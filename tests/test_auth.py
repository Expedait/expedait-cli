"""Tests for token resolution logic."""

import json
from pathlib import Path

import click
import pytest

from expedait_cli.auth import resolve_token, resolve_api_url, resolve_tenant_id


class TestResolveToken:
    def test_env_var_takes_priority(self, monkeypatch, saved_config: Path):
        monkeypatch.setenv("EXPEDAIT_TOKEN", "env-token")
        assert resolve_token(saved_config) == "env-token"

    def test_config_file_fallback(self, saved_config: Path):
        assert resolve_token(saved_config) == "test-token-abc"

    def test_error_when_no_token(self, tmp_path: Path):
        with pytest.raises(click.UsageError, match="Not authenticated"):
            resolve_token(tmp_path / "missing.json")


class TestResolveApiUrl:
    def test_explicit_wins(self, saved_config: Path):
        assert resolve_api_url("http://custom:9000", saved_config) == "http://custom:9000"

    def test_env_var(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("EXPEDAIT_API_URL", "http://env:9000")
        assert resolve_api_url(None, tmp_path / "missing.json") == "http://env:9000"

    def test_config_file(self, saved_config: Path):
        assert resolve_api_url(None, saved_config) == "http://localhost:8000"

    def test_default(self, tmp_path: Path):
        assert resolve_api_url(None, tmp_path / "missing.json") == "https://app.expedait.org"

    def test_strips_trailing_slash(self):
        assert resolve_api_url("http://host:8000/") == "http://host:8000"


class TestResolveTenantId:
    def test_explicit_wins(self, saved_config: Path):
        assert resolve_tenant_id(42, saved_config) == 42

    def test_env_var(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("EXPEDAIT_TENANT_ID", "7")
        assert resolve_tenant_id(None, tmp_path / "missing.json") == 7

    def test_config_file(self, saved_config: Path):
        assert resolve_tenant_id(None, saved_config) == 1

    def test_none_when_missing(self, tmp_path: Path):
        assert resolve_tenant_id(None, tmp_path / "missing.json") is None
