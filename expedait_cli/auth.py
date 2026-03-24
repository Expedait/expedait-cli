"""Token resolution: env var > config file > error."""

from __future__ import annotations

import os

import click

from .config import load_config


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


def resolve_tenant_id(explicit: int | None = None, config_path=None) -> int | None:
    """Return tenant ID from flag > env > config."""
    if explicit is not None:
        return explicit
    env = os.environ.get("EXPEDAIT_TENANT_ID")
    if env:
        return int(env)
    cfg = load_config(config_path)
    tid = cfg.get("tenant_id")
    if tid is not None:
        return int(tid)
    return None
