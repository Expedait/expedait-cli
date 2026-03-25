"""Page commands: list, get, full, download."""

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
def pages() -> None:
    """Manage pages."""


@pages.command("list")
@click.option("--project-id", required=False, type=int, default=None, help="Project ID to list pages for.")
@click.pass_context
def list_pages(ctx: click.Context, project_id: int | None) -> None:
    """List pages in a project."""
    project_id = resolve_project_id(project_id)
    if project_id is None:
        raise click.UsageError(
            "No project ID given. Pass --project-id or run 'expedait init'."
        )
    client = _make_client(ctx)
    try:
        data = client.list_pages(project_id)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not _is_tty()):
        output(data, "json")
    else:
        rows = [
            {"id": p["id"], "title": p["title"], "state": p.get("state", ""), "version": p.get("version", "")}
            for p in data
        ]
        output(rows, "text")


@pages.command("get")
@click.argument("page_id", type=int)
@click.pass_context
def get_page(ctx: click.Context, page_id: int) -> None:
    """Print page content (markdown)."""
    client = _make_client(ctx)
    try:
        data = client.get_page(page_id)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json":
        output(data, "json")
    else:
        click.echo(data.get("content") or "(empty page)")


@pages.command("full")
@click.argument("page_id", type=int)
@click.pass_context
def full_page(ctx: click.Context, page_id: int) -> None:
    """Get page with full context (comments, dependencies, lock status)."""
    client = _make_client(ctx)
    try:
        data = client.get_page_full(page_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@pages.command("download")
@click.argument("page_id", type=int)
@click.option("--output-dir", type=click.Path(), default=".expedait/context", help="Extract to directory.")
@click.option("--download-format", type=click.Choice(["markdown", "json"]), default="markdown", help="Content format.")
@click.pass_context
def download_page(ctx: click.Context, page_id: int, output_dir: str, download_format: str) -> None:
    """Download page as ZIP and extract."""
    client = _make_client(ctx)
    try:
        data = client.download_page(page_id, fmt=download_format)
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
