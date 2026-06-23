"""Context command: get the assembled LLM context for a deliverable.

This is the read-only context *snapshot* fed to the LLM for one deliverable
(dependency deliverables, linked external sources, uploaded files, aggregate
sizes). It is distinct from ``projects download``, which is the whole-project
on-disk spec snapshot.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

import click

from ..auth import resolve_api_url, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import is_tty, output


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)


@click.group()
def context() -> None:
    """Inspect the assembled LLM context for a deliverable."""


@context.command("get")
@click.argument("deliverable_id", type=int)
@click.pass_context
def get_context(ctx: click.Context, deliverable_id: int) -> None:
    """Show the LLM context snapshot for a deliverable."""
    client = _make_client(ctx)
    try:
        data = client.get_deliverable_context(deliverable_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


# --------------------------------------------------------------------------
# Context files — attachments that feed a deliverable's (or objective's) LLM
# context. Works on any deliverable id, objectives included. External source
# links (Notion/GitHub/...) are created through the web app's integration
# flows, not here; the CLI owns the file half of the context surface.
# --------------------------------------------------------------------------


@context.command("files")
@click.argument("deliverable_id", type=int)
@click.pass_context
def list_files(ctx: click.Context, deliverable_id: int) -> None:
    """List the context files attached to a deliverable."""
    client = _make_client(ctx)
    try:
        data = client.list_deliverable_files(deliverable_id)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(data, "json")
        return
    rows = [
        {
            "id": f.get("id"),
            "filename": f.get("filename"),
            "file_type": f.get("file_type") or "",
            "size": f.get("file_size") or "",
            "excluded": f.get("excluded_from_context", False),
        }
        for f in data
    ]
    output(rows, "text")


@context.command("add")
@click.argument("deliverable_id", type=int)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--name", default=None, help="Override the stored filename (defaults to the file's name).")
@click.pass_context
def add_file(ctx: click.Context, deliverable_id: int, file_path: str, name: str | None) -> None:
    """Upload a context file to a deliverable (re-upload by name replaces it)."""
    path = Path(file_path)
    filename = name or path.name
    content_type = mimetypes.guess_type(filename)[0]
    data = path.read_bytes()
    client = _make_client(ctx)
    try:
        result = client.upload_deliverable_file(
            deliverable_id, filename, data, content_type,
        )
    finally:
        client.close()
    output(result, ctx.obj.get("fmt"))


@context.command("file-content")
@click.argument("file_id", type=int)
@click.pass_context
def file_content(ctx: click.Context, file_id: int) -> None:
    """Print the parsed text a context file contributes to the LLM context."""
    client = _make_client(ctx)
    try:
        data = client.get_deliverable_file_content(file_id)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json":
        output(data, "json")
    else:
        click.echo(data.get("content") or "(empty / not yet parsed)")


@context.command("download-file")
@click.argument("file_id", type=int)
@click.option("--output", "-o", "output_path", type=click.Path(dir_okay=False), required=True, help="Write the file bytes here.")
@click.pass_context
def download_file(ctx: click.Context, file_id: int, output_path: str) -> None:
    """Download a context file's raw bytes to disk."""
    client = _make_client(ctx)
    try:
        data = client.download_deliverable_file(file_id)
    finally:
        client.close()
    Path(output_path).write_bytes(data)
    click.echo(f"Wrote {len(data)} bytes to {Path(output_path).resolve()}")


@context.command("remove-file")
@click.argument("file_id", type=int)
@click.pass_context
def remove_file(ctx: click.Context, file_id: int) -> None:
    """Delete a context file from a deliverable."""
    client = _make_client(ctx)
    try:
        client.delete_deliverable_file(file_id)
    finally:
        client.close()
    click.echo("Context file deleted.")


@context.command("set-file")
@click.argument("file_id", type=int)
@click.option("--exclude/--include", "exclude", required=True, help="Exclude (or include) this file from the LLM context.")
@click.pass_context
def set_file(ctx: click.Context, file_id: int, exclude: bool) -> None:
    """Include or exclude a context file from the deliverable's LLM context."""
    client = _make_client(ctx)
    try:
        result = client.set_deliverable_file_excluded(file_id, exclude)
    finally:
        client.close()
    output(result, ctx.obj.get("fmt"))
