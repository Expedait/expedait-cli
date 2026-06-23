"""HTTP client wrapper for Expedait API."""

from __future__ import annotations

from typing import Any

import click
import httpx


class BackendError(Exception):
    """A non-2xx API response, raised by the op-safe request path so the
    multi-op engine (``ops.run_ops``) can record a per-op failure and keep
    going, instead of aborting the whole command the way ``_check`` does."""

    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(f"backend error {status}: {body}")


class ExpedaitClient:
    """Thin wrapper around httpx with auth and tenant headers."""

    def __init__(self, api_url: str, token: str, tenant_id: int | None = None):
        self.tenant_id = tenant_id
        headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
        if tenant_id is not None:
            headers["X-Active-Tenant-Id"] = str(tenant_id)
        # follow_redirects: collection endpoints are mounted at "/", so the
        # API 307-redirects e.g. /api/v1/deliverables -> /api/v1/deliverables/.
        self._http = httpx.Client(
            base_url=api_url, headers=headers, timeout=30.0, follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    # -- helpers ----------------------------------------------------------

    def _check(self, resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise click.UsageError(
                "Authentication failed (401). Run 'expedait auth login'."
            )
        if resp.status_code == 403:
            raise click.UsageError(
                "Permission denied (403). Check your tenant access."
            )
        if resp.status_code == 404:
            raise click.UsageError("Resource not found (404).")
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise click.ClickException(f"API error {resp.status_code}: {detail}")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make request, handle errors, return parsed JSON."""
        resp = self._http.request(method, path, **kwargs)
        self._check(resp)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def _request_raw(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Make request, handle errors, return raw response."""
        resp = self._http.request(method, path, **kwargs)
        self._check(resp)
        return resp

    def _request_op(self, method: str, path: str, **kwargs: Any) -> Any:
        """Like ``_request`` but raises :class:`BackendError` on any non-2xx
        instead of a click error, so the multi-op engine can capture the
        failure per-op and report it without aborting the command."""
        resp = self._http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                body = body.get("detail", body)
            except Exception:
                body = resp.text
            raise BackendError(resp.status_code, body)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def _with_tenant(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Mirror the MCP write tools, which include ``tenant_id`` in create
        bodies. The backend also reads the ``X-Active-Tenant-Id`` header, so we
        only add it when we actually know the tenant."""
        if self.tenant_id is not None and "tenant_id" not in payload:
            payload = {**payload, "tenant_id": self.tenant_id}
        return payload

    # -- auth -------------------------------------------------------------

    @staticmethod
    def login(api_url: str, email: str, password: str) -> dict[str, Any]:
        """POST /api/v1/auth/login — returns token payload."""
        resp = httpx.post(
            f"{api_url}/api/v1/auth/login",
            json={"email": email, "password": password},
            timeout=15.0,
        )
        if resp.status_code == 401:
            raise click.UsageError("Invalid email or password.")
        if resp.status_code >= 400:
            raise click.ClickException(f"Login failed ({resp.status_code}).")
        return resp.json()

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/auth/me")

    # -- projects ---------------------------------------------------------

    def list_projects(
        self, skip: int | None = None, limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if skip is not None:
            params["skip"] = skip
        if limit is not None:
            params["limit"] = limit
        return self._request("GET", "/api/v1/projects", params=params or None)

    def get_project(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{project_id}")

    def get_workspace(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{project_id}/workspace")

    def download_project(self, project_id: int) -> bytes:
        resp = self._request_raw("GET", f"/api/v1/projects/{project_id}/download")
        return resp.content

    # -- deliverables -----------------------------------------------------

    def list_deliverables(
        self, project_id: int, skip: int = 0, limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/api/v1/deliverables",
            params={"project_id": project_id, "skip": skip, "limit": limit},
        )

    def get_deliverable(self, deliverable_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/deliverables/{deliverable_id}")

    def get_deliverable_full(self, deliverable_id: int) -> dict[str, Any]:
        """Full payload: dependencies, comments, versions, lock status."""
        return self._request("GET", f"/api/v1/deliverables/{deliverable_id}/full")

    def get_deliverable_type(self, type_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/deliverables/types/{type_id}")

    def get_deliverable_sources(self, deliverable_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/deliverables/{deliverable_id}/sources")

    # -- context files (attachments feeding a deliverable's LLM context) ---

    def list_deliverable_files(self, deliverable_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/deliverables/{deliverable_id}/files")

    def upload_deliverable_file(
        self, deliverable_id: int, filename: str, data: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload a context file. Re-upload with the same filename replaces it."""
        files = {"file": (filename, data, content_type or "application/octet-stream")}
        return self._request(
            "POST", f"/api/v1/deliverables/{deliverable_id}/files", files=files,
        )

    def get_deliverable_file_content(self, file_id: int) -> dict[str, Any]:
        """Parsed markdown text of a context file (empty for unparsed/binary)."""
        return self._request("GET", f"/api/v1/deliverables/files/{file_id}/content")

    def download_deliverable_file(self, file_id: int) -> bytes:
        resp = self._request_raw("GET", f"/api/v1/deliverables/files/{file_id}")
        return resp.content

    def delete_deliverable_file(self, file_id: int) -> Any:
        return self._request("DELETE", f"/api/v1/deliverables/files/{file_id}")

    def set_deliverable_file_excluded(
        self, file_id: int, excluded: bool,
    ) -> dict[str, Any]:
        """Toggle whether a file is fed into the deliverable's LLM context."""
        return self._request(
            "PATCH", f"/api/v1/deliverables/files/{file_id}",
            json={"excluded_from_context": excluded},
        )

    def list_deliverable_types(
        self, skip: int = 0, limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/api/v1/deliverables/types",
            params={"skip": skip, "limit": limit},
        )

    # -- deliverable writes (op-safe: raise BackendError) -----------------

    def create_deliverable(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a new deliverable. Mirrors write_deliverable's `create` op."""
        return self._request_op(
            "POST", "/api/v1/deliverables/", json=payload,
        )

    def update_deliverable(self, deliverable_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """PUT — used for both `edit` (content) and `rename` (title); the
        backend's DeliverableUpdate is exclude_unset so a title-only body
        renames without touching content."""
        return self._request_op(
            "PUT", f"/api/v1/deliverables/{deliverable_id}", json=payload,
        )

    def save_deliverable_version(
        self, deliverable_id: int, reason: str | None = None,
    ) -> dict[str, Any]:
        return self._request_op(
            "POST", f"/api/v1/deliverables/{deliverable_id}/versions",
            json={"comment": reason},
        )

    def set_deliverable_state(
        self, deliverable_id: int, to_state: str, reason: str | None = None,
    ) -> dict[str, Any]:
        return self._request_op(
            "PUT", f"/api/v1/deliverables/{deliverable_id}/state",
            json={"to_state": to_state, "comment": reason},
        )

    # -- deliverable type writes (Process Designer cards) -----------------

    def create_deliverable_type(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op(
            "POST", "/api/v1/deliverables/types", json=self._with_tenant(payload),
        )

    def update_deliverable_type(self, type_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op(
            "PUT", f"/api/v1/deliverables/types/{type_id}", json=payload,
        )

    def delete_deliverable_type(self, type_id: int) -> Any:
        return self._request_op("DELETE", f"/api/v1/deliverables/types/{type_id}")

    def get_deliverable_type_usage_impact(self, type_id: int) -> dict[str, Any]:
        return self._request_op(
            "GET", f"/api/v1/deliverables/types/{type_id}/usage-impact",
        )

    def set_deliverable_type_dependencies(
        self, type_id: int, dependency_ids: list[int],
    ) -> Any:
        return self._request_op(
            "PUT", f"/api/v1/deliverables/types/{type_id}/dependencies",
            json={"dependency_ids": dependency_ids},
        )

    def set_deliverable_type_owner_roles(
        self, type_id: int, role_ids: list[int],
    ) -> Any:
        return self._request_op(
            "PUT", f"/api/v1/deliverables/types/{type_id}/owner-roles",
            json={"role_ids": role_ids},
        )

    def download_deliverable(self, deliverable_id: int) -> bytes:
        resp = self._request_raw(
            "GET", f"/api/v1/deliverables/{deliverable_id}/download",
        )
        return resp.content

    def get_objective_overview(self, deliverable_id: int) -> dict[str, Any]:
        """Objective metadata + descendant tree. 400 if not an objective."""
        resp = self._http.request(
            "GET", f"/api/v1/deliverables/{deliverable_id}/objective-overview",
        )
        if resp.status_code == 400:
            raise click.UsageError(
                f"Deliverable {deliverable_id} is not an objective."
            )
        self._check(resp)
        return resp.json()

    def get_deliverable_context(self, deliverable_id: int) -> dict[str, Any]:
        """Read-only LLM context snapshot for a deliverable."""
        return self._request(
            "GET", f"/api/v1/deliverables/{deliverable_id}/context-summary",
        )

    # -- review issues ----------------------------------------------------

    def list_review_issues(
        self, deliverable_id: int, state: str = "all",
    ) -> list[dict[str, Any]]:
        # Backend default (no state param) is open + muted == 'all'.
        params = {} if state == "all" else {"state": state}
        return self._request(
            "GET", f"/api/v1/deliverables/{deliverable_id}/issues", params=params,
        )

    def mute_review_issue(
        self, issue_id: int, muted: bool = True, note: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"state": "muted" if muted else "open"}
        if muted and note is not None:
            payload["muted_note"] = note
        return self._request(
            "PATCH", f"/api/v1/deliverables/issues/{issue_id}", json=payload,
        )

    # -- comments ---------------------------------------------------------

    def list_comments(self, deliverable_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/deliverables/{deliverable_id}/comments")

    def create_comment(self, deliverable_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/v1/deliverables/{deliverable_id}/comments", json=data,
        )

    def resolve_comment(self, deliverable_id: int, comment_id: int) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/deliverables/{deliverable_id}/comments/{comment_id}",
            params={"is_resolved": "true"},
        )

    def delete_comment(self, deliverable_id: int, comment_id: int) -> Any:
        return self._request(
            "DELETE", f"/api/v1/deliverables/{deliverable_id}/comments/{comment_id}",
        )

    # -- processes (project types) — reads --------------------------------

    def list_processes(self, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/api/v1/projects/types", params={"skip": skip, "limit": limit},
        )

    def get_process_type(self, process_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/types/{process_id}")

    def get_process_phases(self, process_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/projects/types/{process_id}/phases")

    def get_process_rows(self, process_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/projects/types/{process_id}/rows")

    # -- processes — op-safe writes ---------------------------------------

    def create_process(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op(
            "POST", "/api/v1/projects/types", json=self._with_tenant(payload),
        )

    def update_process(self, process_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op("PUT", f"/api/v1/projects/types/{process_id}", json=payload)

    def duplicate_process(self, process_id: int) -> dict[str, Any]:
        return self._request_op("POST", f"/api/v1/projects/types/{process_id}/duplicate")

    def delete_process(self, process_id: int) -> Any:
        return self._request_op("DELETE", f"/api/v1/projects/types/{process_id}")

    def create_phase(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op(
            "POST", "/api/v1/projects/phases", json=self._with_tenant(payload),
        )

    def update_phase(self, phase_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op("PUT", f"/api/v1/projects/phases/{phase_id}", json=payload)

    def delete_phase(self, phase_id: int) -> Any:
        return self._request_op("DELETE", f"/api/v1/projects/phases/{phase_id}")

    def create_phase_row(self, phase_id: int, position: float) -> dict[str, Any]:
        return self._request_op(
            "POST", f"/api/v1/projects/phases/{phase_id}/rows",
            json={"position": position},
        )

    def update_phase_row(self, row_id: int, position: float) -> dict[str, Any]:
        return self._request_op(
            "PUT", f"/api/v1/projects/rows/{row_id}", json={"position": position},
        )

    def delete_phase_row(self, row_id: int) -> Any:
        return self._request_op("DELETE", f"/api/v1/projects/rows/{row_id}")

    # -- roles (owner-role pool) ------------------------------------------

    def list_roles(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/projects/roles")

    def create_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op(
            "POST", "/api/v1/projects/roles", json=self._with_tenant(payload),
        )

    def update_role(self, role_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_op("PUT", f"/api/v1/projects/roles/{role_id}", json=payload)

    def delete_role(self, role_id: int) -> Any:
        return self._request_op("DELETE", f"/api/v1/projects/roles/{role_id}")
