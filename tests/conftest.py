"""Shared fixtures for CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    """Return a temp config file path."""
    return tmp_path / "config.json"


@pytest.fixture()
def saved_config(config_path: Path) -> Path:
    """Write a valid config and return its path."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        "api_url": "http://localhost:8000",
        "token": "test-token-abc",
        "tenant_id": 1,
    }))
    return config_path
