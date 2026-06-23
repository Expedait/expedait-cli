"""Tests for ExpedaitClient HTTP wrapper."""

import click
import httpx
import pytest

from expedait_cli.client import ExpedaitClient


class TestClientHeaders:
    def test_auth_header_set(self):
        c = ExpedaitClient("http://x", "tok123")
        assert c._http.headers["authorization"] == "Bearer tok123"
        c.close()

    def test_tenant_header_set(self):
        c = ExpedaitClient("http://x", "tok", tenant_id=5)
        assert c._http.headers["x-active-tenant-id"] == "5"
        c.close()

    def test_no_tenant_header_when_none(self):
        c = ExpedaitClient("http://x", "tok")
        assert "x-active-tenant-id" not in c._http.headers
        c.close()


class TestClientErrorMapping:
    def test_401_raises_usage_error(self, httpx_mock):
        httpx_mock.add_response(status_code=401)
        c = ExpedaitClient("http://x", "tok")
        with pytest.raises(click.UsageError, match="Authentication failed"):
            c._request("GET", "/test")
        c.close()

    def test_403_raises_usage_error(self, httpx_mock):
        httpx_mock.add_response(status_code=403)
        c = ExpedaitClient("http://x", "tok")
        with pytest.raises(click.UsageError, match="Permission denied"):
            c._request("GET", "/test")
        c.close()

    def test_404_raises_usage_error(self, httpx_mock):
        httpx_mock.add_response(status_code=404)
        c = ExpedaitClient("http://x", "tok")
        with pytest.raises(click.UsageError, match="not found"):
            c._request("GET", "/test")
        c.close()

    def test_500_raises_click_exception(self, httpx_mock):
        httpx_mock.add_response(status_code=500, json={"detail": "boom"})
        c = ExpedaitClient("http://x", "tok")
        with pytest.raises(click.ClickException, match="boom"):
            c._request("GET", "/test")
        c.close()


class TestClientMethods:
    def test_list_projects(self, httpx_mock):
        httpx_mock.add_response(json=[{"id": 1, "name": "P1"}])
        c = ExpedaitClient("http://x", "tok")
        result = c.list_projects()
        assert result == [{"id": 1, "name": "P1"}]
        c.close()

    def test_get_deliverable(self, httpx_mock):
        httpx_mock.add_response(json={"id": 1, "content": "# Hello"})
        c = ExpedaitClient("http://x", "tok")
        result = c.get_deliverable(1)
        assert result["content"] == "# Hello"
        c.close()

    def test_objective_overview_400_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=400, json={"detail": "not an objective"})
        c = ExpedaitClient("http://x", "tok")
        with pytest.raises(click.UsageError, match="not an objective"):
            c.get_objective_overview(1)
        c.close()

    def test_mute_review_issue_payload(self, httpx_mock):
        httpx_mock.add_response(json={"id": 7, "state": "muted"})
        c = ExpedaitClient("http://x", "tok")
        result = c.mute_review_issue(7, muted=True, note="by design")
        assert result["state"] == "muted"
        request = httpx_mock.get_request()
        assert request.method == "PATCH"
        import json as _json
        assert _json.loads(request.content) == {"state": "muted", "muted_note": "by design"}
        c.close()

    def test_delete_comment_no_content(self, httpx_mock):
        httpx_mock.add_response(status_code=204)
        c = ExpedaitClient("http://x", "tok")
        assert c.delete_comment(1, 2) is None
        c.close()

    def test_download_project(self, httpx_mock):
        httpx_mock.add_response(content=b"PK\x03\x04fake-zip")
        c = ExpedaitClient("http://x", "tok")
        result = c.download_project(1)
        assert result.startswith(b"PK")
        c.close()

    def test_create_comment(self, httpx_mock):
        httpx_mock.add_response(json={"id": 10, "comment_text": "test"})
        c = ExpedaitClient("http://x", "tok")
        result = c.create_comment(1, {"comment_text": "test"})
        assert result["id"] == 10
        c.close()

    def test_login_success(self, httpx_mock):
        httpx_mock.add_response(json={"access_token": "tok", "token_type": "bearer"})
        result = ExpedaitClient.login("http://x", "a@b.com", "pass")
        assert result["access_token"] == "tok"

    def test_login_invalid_credentials(self, httpx_mock):
        httpx_mock.add_response(status_code=401)
        with pytest.raises(click.UsageError, match="Invalid email"):
            ExpedaitClient.login("http://x", "a@b.com", "wrong")


class TestContextFileUpload:
    def test_multipart_field_and_tenant_header(self, httpx_mock):
        """Upload must send a multipart part named 'file' and carry the tenant
        header — the context-file command tests mock the client wholesale, so
        this is the only check of the real outgoing request shape."""
        httpx_mock.add_response(
            json={"id": 3, "filename": "ref.md"},
            url="http://x/api/v1/deliverables/1/files",
        )
        c = ExpedaitClient("http://x", "tok", tenant_id=7)
        result = c.upload_deliverable_file(1, "ref.md", b"# Ref", "text/markdown")
        c.close()
        assert result["id"] == 3
        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert req.headers["x-active-tenant-id"] == "7"
        body = req.content
        assert b'name="file"' in body
        assert b"ref.md" in body
        assert b"# Ref" in body


class TestOpSafeErrors:
    def test_request_op_raises_backend_error(self, httpx_mock):
        from expedait_cli.client import BackendError
        httpx_mock.add_response(status_code=423, json={"detail": "locked"})
        c = ExpedaitClient("http://x", "tok")
        with pytest.raises(BackendError) as exc:
            c._request_op("PUT", "/api/v1/deliverables/1", json={"content": "x"})
        c.close()
        assert exc.value.status == 423
        assert "locked" in str(exc.value.body)
