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

    def test_get_page(self, httpx_mock):
        httpx_mock.add_response(json={"id": 1, "content": "# Hello"})
        c = ExpedaitClient("http://x", "tok")
        result = c.get_page(1)
        assert result["content"] == "# Hello"
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
