"""Token resolution: env var > config file > error."""

from __future__ import annotations

import os

import click

from .config import load_config
from .settings import load_settings


def resolve_token(config_path=None) -> str:
    """Return a bearer token or raise click.UsageError."""
    # 1. Environment variable
    token = os.environ.get("EXPEDAIT_TOKEN")
    if token:
        return token

    # 2. Config file
    cfg = load_config(config_path)
    token = cfg.get("token")
    if token:
        return token

    raise click.UsageError(
        "Not authenticated. Run 'expedait auth login' or set EXPEDAIT_TOKEN."
    )


def resolve_api_url(explicit: str | None = None, config_path=None) -> str:
    """Return API URL from flag > env > config > default."""
    if explicit:
        return explicit.rstrip("/")
    env = os.environ.get("EXPEDAIT_API_URL")
    if env:
        return env.rstrip("/")
    cfg = load_config(config_path)
    url = cfg.get("api_url")
    if url:
        return url.rstrip("/")
    return "https://app.expedait.org"


def resolve_tenant_id(
    explicit: int | None = None,
    config_path=None,
    settings_path=None,
) -> int | None:
    """Return tenant ID from flag > env > local settings > config."""
    if explicit is not None:
        return explicit
    env = os.environ.get("EXPEDAIT_TENANT_ID")
    if env:
        return int(env)
    # Local project settings
    settings = load_settings(settings_path)
    tid = settings.get("tenant_id")
    if tid is not None:
        return int(tid)
    # Global config
    cfg = load_config(config_path)
    tid = cfg.get("tenant_id")
    if tid is not None:
        return int(tid)
    return None


def resolve_project_id(
    explicit: int | None = None,
    settings_path=None,
) -> int | None:
    """Return project ID from flag > env > local settings."""
    if explicit is not None:
        return explicit
    env = os.environ.get("EXPEDAIT_PROJECT_ID")
    if env:
        return int(env)
    settings = load_settings(settings_path)
    pid = settings.get("project_id")
    if pid is not None:
        return int(pid)
    return None
