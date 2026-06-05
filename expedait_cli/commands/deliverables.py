"""Deliverable commands: list, get, inspect, download.

A *deliverable* is an individual spec document (formerly "page"/"outcome").
An *objective* is a deliverable that nests child deliverables beneath it via
``parent_deliverable_id`` — see the ``objectives`` command group.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import click

from ..auth import resolve_api_url, resolve_project_id, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import is_tty, output


# Sections that `deliverables get --include` understands, mirroring the MCP
# `get_deliverable` tool's section reads.
INCLUDE_SECTIONS = (
    "meta",
    "content",
    "template",
    "requirements",
    "writer_instructions",
    "dependencies",
    "external_context",
    "score",
    "comments",
    "versions",
)


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)


def _meta_view(deliverable: dict) -> dict:
    return {
        "id": deliverable.get("id"),
        "title": deliverable.get("title"),
        "state": deliverable.get("state"),
        "version": deliverable.get("version"),
        "owner_user_id": deliverable.get("owner_user_id"),
        "is_locked": deliverable.get("is_locked"),
        "project_id": deliverable.get("project_id"),
        "deliverable_type_id": deliverable.get("deliverable_type_id"),
        # Non-null means this deliverable is a child nested under an objective.
        "parent_deliverable_id": deliverable.get("parent_deliverable_id"),
    }


def _parse_include(raw: str) -> list[str]:
    sections: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        if name not in INCLUDE_SECTIONS:
            raise click.UsageError(
                f"Unknown include section: {name!r}. "
                f"Valid: {', '.join(INCLUDE_SECTIONS)}"
            )
        if name not in sections:
            sections.append(name)
    return sections or ["content"]


def _assemble_sections(
    client: ExpedaitClient, deliverable_id: int, include: list[str],
) -> dict:
    """Fetch and assemble the requested deliverable sections."""
    deliverable = client.get_deliverable(deliverable_id)
    result: dict = {"id": deliverable_id}

    if "meta" in include:
        result["meta"] = _meta_view(deliverable)
    if "content" in include:
        result["content"] = deliverable.get("content") or ""

    if {"template", "requirements", "writer_instructions"} & set(include):
        dtype = client.get_deliverable_type(deliverable["deliverable_type_id"])
        # The backend stores writer guidance under `instructions`.
        for section, field in (
            ("template", "template_content"),
            ("requirements", "deliverable_requirements"),
            ("writer_instructions", "instructions"),
        ):
            if section in include:
                result[section] = dtype.get(field) or ""

    if {"dependencies", "score", "comments", "versions"} & set(include):
        full = client.get_deliverable_full(deliverable_id)
        if "dependencies" in include:
            result["dependencies"] = full.get("dependencies") or []
            result["is_locked"] = full.get("is_locked")
            result["unmet_dependencies"] = full.get("unmet_dependencies") or []
        if "comments" in include:
            result["comments"] = full.get("comments") or []
        if "versions" in include:
            result["versions"] = full.get("versions") or []
        if "score" in include:
            versions = full.get("versions") or []
            latest = versions[-1] if versions and isinstance(versions[-1], dict) else None
            result["score"] = (
                {
                    "score": latest.get("score"),
                    "score_breakdown": latest.get("score_breakdown"),
                    "scoring_status": latest.get("scoring_status"),
                    "version_number": latest.get("version_number"),
                }
                if latest
                else None
            )

    if "external_context" in include:
        result["external_context"] = client.get_deliverable_sources(deliverable_id) or []

    return result


@click.group()
def deliverables() -> None:
    """Manage deliverables (spec documents)."""


@deliverables.command("list")
@click.option("--project-id", required=False, type=int, default=None, help="Project ID to list deliverables for.")
@click.pass_context
def list_deliverables(ctx: click.Context, project_id: int | None) -> None:
    """List deliverables in a project."""
    project_id = resolve_project_id(project_id)
    if project_id is None:
        raise click.UsageError(
            "No project ID given. Pass --project-id or run 'expedait init'."
        )
    client = _make_client(ctx)
    try:
        data = client.list_deliverables(project_id)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(data, "json")
    else:
        rows = [
            {
                "id": d["id"],
                "title": d["title"],
                "state": d.get("state", ""),
                "version": d.get("version", ""),
                "parent": d.get("parent_deliverable_id") or "",
            }
            for d in data
        ]
        output(rows, "text")


@deliverables.command("get")
@click.argument("deliverable_id", type=int)
@click.option(
    "--include",
    default="content",
    help=(
        "Comma-separated sections to include: "
        f"{', '.join(INCLUDE_SECTIONS)}. Defaults to 'content'."
    ),
)
@click.pass_context
def get_deliverable(ctx: click.Context, deliverable_id: int, include: str) -> None:
    """Print a deliverable. Defaults to its markdown content."""
    sections = _parse_include(include)
    client = _make_client(ctx)
    try:
        result = _assemble_sections(client, deliverable_id, sections)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    # Back-compat: a bare `get` (content only) prints raw markdown in text mode.
    if sections == ["content"] and fmt != "json":
        click.echo(result.get("content") or "(empty deliverable)")
    else:
        output(result, fmt)


@deliverables.command("inspect")
@click.argument("deliverable_id", type=int)
@click.pass_context
def inspect_deliverable(ctx: click.Context, deliverable_id: int) -> None:
    """Get a deliverable with full context (comments, dependencies, lock status)."""
    client = _make_client(ctx)
    try:
        data = client.get_deliverable_full(deliverable_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@deliverables.command("download")
@click.argument("deliverable_id", type=int)
@click.option("--output-dir", type=click.Path(), default=".expedait/context", help="Extract to directory.")
@click.pass_context
def download_deliverable(ctx: click.Context, deliverable_id: int, output_dir: str) -> None:
    """Download a deliverable as a ZIP and extract."""
    client = _make_client(ctx)
    try:
        data = client.download_deliverable(deliverable_id)
    finally:
        client.close()

    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)
    click.echo(f"Extracted to {dest.resolve()}")


# --------------------------------------------------------------------------
# Deprecated `pages` alias — forwards to `deliverables`, warns, drop next
# release. Reuses the same command callbacks so behaviour stays identical.
# --------------------------------------------------------------------------


@click.group(hidden=True)
def pages() -> None:
    """[Deprecated] Renamed to 'deliverables'."""
    click.echo(
        "Warning: 'pages' is deprecated and will be removed next release. "
        "Use 'deliverables' instead.",
        err=True,
    )


pages.add_command(list_deliverables, "list")
pages.add_command(get_deliverable, "get")
pages.add_command(inspect_deliverable, "inspect")
pages.add_command(download_deliverable, "download")
