"""HTTP client wrapper for Expedait API."""

from __future__ import annotations

from typing import Any

import click
import httpx


class ExpedaitClient:
    """Thin wrapper around httpx with auth and tenant headers."""

    def __init__(self, api_url: str, token: str, tenant_id: int | None = None):
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

    def list_projects(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/projects")

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
