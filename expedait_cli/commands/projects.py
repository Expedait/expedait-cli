"""Project commands: list, get, download."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import click

from ..auth import resolve_api_url, resolve_project_id, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import output


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)


@click.group()
def projects() -> None:
    """Manage projects."""


@projects.command("list")
@click.pass_context
def list_projects(ctx: click.Context) -> None:
    """List all projects in the tenant."""
    client = _make_client(ctx)
    try:
        data = client.list_projects()
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not _is_tty()):
        output(data, "json")
    else:
        rows = [
            {"id": p["id"], "name": p["name"], "type": p.get("project_type_name", ""), "state": p.get("state", "")}
            for p in data
        ]
        output(rows, "text")


@projects.command("get")
@click.argument("project_id", type=int)
@click.pass_context
def get_project(ctx: click.Context, project_id: int) -> None:
    """Get project details."""
    client = _make_client(ctx)
    try:
        data = client.get_project(project_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@projects.command("workspace")
@click.argument("project_id", type=int, required=False, default=None)
@click.pass_context
def get_workspace(ctx: click.Context, project_id: int | None) -> None:
    """Show a project's workspace: deliverables grouped by phase.

    Mirrors the MCP `get_project_workspace` tool — the structure-aware view the
    flat `deliverables list` can't give you.
    """
    project_id = resolve_project_id(project_id)
    if project_id is None:
        raise click.UsageError(
            "No project ID given. Pass PROJECT_ID or run 'expedait init'."
        )
    client = _make_client(ctx)
    try:
        data = client.get_workspace(project_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@projects.command("download")
@click.argument("project_id", type=int, required=False, default=None)
@click.option("--output-dir", type=click.Path(), default=".expedait/context", help="Extract to directory.")
@click.option("--download-format", type=click.Choice(["markdown", "json"]), default="markdown", help="Content format.")
@click.pass_context
def download_project(ctx: click.Context, project_id: int | None, output_dir: str, download_format: str) -> None:
    """Download all project pages as a ZIP and extract."""
    project_id = resolve_project_id(project_id)
    if project_id is None:
        raise click.UsageError(
            "No project ID given. Pass PROJECT_ID or run 'expedait init'."
        )
    client = _make_client(ctx)
    try:
        data = client.download_project(project_id, fmt=download_format)
    finally:
        client.close()

    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)

    click.echo(f"Extracted to {dest.resolve()}")


def _is_tty() -> bool:
    import sys
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
