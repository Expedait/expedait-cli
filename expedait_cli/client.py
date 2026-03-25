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
        self._http = httpx.Client(base_url=api_url, headers=headers, timeout=30.0)

    def close(self) -> None:
        self._http.close()

    # -- helpers ----------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make request, handle errors, return parsed JSON."""
        resp = self._http.request(method, path, **kwargs)
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
        return resp.json()

    def _request_raw(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Make request, handle errors, return raw response."""
        resp = self._http.request(method, path, **kwargs)
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

    def download_project(self, project_id: int, fmt: str = "markdown") -> bytes:
        resp = self._request_raw(
            "GET", f"/api/v1/projects/{project_id}/download", params={"format": fmt},
        )
        return resp.content

    # -- pages ------------------------------------------------------------

    def list_pages(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/pages", params={"project_id": project_id})

    def get_page(self, page_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/pages/{page_id}")

    def get_page_full(self, page_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/pages/{page_id}/full")

    def download_page(self, page_id: int, fmt: str = "markdown") -> bytes:
        resp = self._request_raw(
            "GET", f"/api/v1/pages/{page_id}/download", params={"format": fmt},
        )
        return resp.content

    # -- comments ---------------------------------------------------------

    def list_comments(self, page_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/pages/{page_id}/comments")

    def create_comment(self, page_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/pages/{page_id}/comments", json=data)

    def resolve_comment(self, comment_id: int) -> dict[str, Any]:
        return self._request("PUT", f"/api/v1/pages/comments/{comment_id}/resolve")

    def delete_comment(self, comment_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/api/v1/pages/comments/{comment_id}")
