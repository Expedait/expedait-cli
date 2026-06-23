"""Deliverable commands: list, get, inspect, download.

A *deliverable* is an individual spec document (formerly "page"/"outcome").
An *objective* is a deliverable that nests child deliverables beneath it via
``parent_deliverable_id`` — see the ``objectives`` command group.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import click

from ..auth import resolve_api_url, resolve_project_id, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import is_tty, output
from ..ops import RefResolver, read_value_arg, render_ops, run_ops


# State enum, shared with `set-state` and the write `set_state` op. Mirrors the
# MCP write_deliverable VALID_STATES.
VALID_STATES = (
    "Not Started", "In Progress", "Review", "Approved", "Completed", "Final",
)
WRITE_OPS_MAX = 10
VALID_WRITE_OPS = ("create", "edit", "rename", "save_version", "set_state")


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


@deliverables.command("types")
@click.pass_context
def list_types(ctx: click.Context) -> None:
    """List deliverable types — find the --type ID that `create` needs.

    Types are workspace-wide (they belong to processes, not a single project);
    use `processes get PROCESS_ID` to see how they're arranged into phases.
    """
    client = _make_client(ctx)
    try:
        data = client.list_deliverable_types()
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(data, "json")
        return
    rows = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "abbreviation": t.get("abbreviation") or "",
            "is_objective": t.get("is_objective", False),
            "phase_id": t.get("phase_id"),
        }
        for t in data
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
# Write surface — mirrors the MCP `write_deliverable` tool. The ergonomic
# subcommands (create/edit/rename/save-version/set-state) each compose a
# single-op ops array and run it through the same engine as `write --ops`, so
# output, error handling, and exit codes stay identical.
# --------------------------------------------------------------------------


def _load_ops(ops_arg: str) -> list[dict]:
    """Load an ops array from `@file.json`, `-` (stdin), or an inline string."""
    raw = read_value_arg(ops_arg)
    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--ops is not valid JSON: {exc}")
    if not isinstance(ops, list):
        raise click.UsageError("--ops must be a JSON array of op objects.")
    return ops


def _preflight_validate(ops: list[dict]) -> None:
    """Reject the whole call before any backend write if op shape or $last/@ref
    ordering is wrong — mirrors the MCP write_deliverable pre-flight."""
    if not ops:
        raise click.UsageError("ops must be non-empty.")
    if len(ops) > WRITE_OPS_MAX:
        raise click.UsageError(f"too many ops; max {WRITE_OPS_MAX}.")

    last_known = False
    bound_refs: set = set()
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise click.UsageError(f"ops[{i}] must be an object.")
        op_type = op.get("op")
        if op_type not in VALID_WRITE_OPS:
            raise click.UsageError(
                f"ops[{i}].op invalid: {op_type!r}. Valid: {', '.join(VALID_WRITE_OPS)}"
            )
        if op_type == "create":
            for required in ("project_id", "deliverable_type_id", "title"):
                if op.get(required) in (None, ""):
                    raise click.UsageError(f"ops[{i}] (create): {required} is required.")
            parent = op.get("parent_deliverable_id")
            if parent is not None and not isinstance(parent, int):
                raise click.UsageError(
                    f"ops[{i}] (create): parent_deliverable_id must be int or omitted."
                )
            ref = op.get("ref")
            if ref is not None:
                if not isinstance(ref, str) or not ref.strip():
                    raise click.UsageError(f"ops[{i}] (create): ref must be a non-empty string.")
                bound_refs.add(ref)
            last_known = True
            continue

        raw_id = op.get("id")
        if raw_id == "$last":
            if not last_known:
                raise click.UsageError(
                    f"ops[{i}] ({op_type}): $last has no preceding id."
                )
        elif isinstance(raw_id, str) and raw_id.startswith("@"):
            if raw_id[1:] not in bound_refs:
                raise click.UsageError(
                    f"ops[{i}] ({op_type}): unknown ref {raw_id!r} "
                    "(bind it with an earlier create op that sets ref)."
                )
            last_known = True
        elif isinstance(raw_id, int):
            last_known = True
        else:
            raise click.UsageError(
                f"ops[{i}] ({op_type}): id must be int, '$last', or '@name'."
            )

        if op_type == "edit":
            if op.get("content") is None:
                raise click.UsageError(f"ops[{i}] (edit): content is required.")
        elif op_type == "rename":
            if not isinstance(op.get("title"), str) or not op["title"].strip():
                raise click.UsageError(f"ops[{i}] (rename): a non-empty title is required.")
        elif op_type == "set_state":
            if op.get("state") not in VALID_STATES:
                raise click.UsageError(
                    f"ops[{i}] (set_state): state {op.get('state')!r} invalid. "
                    f"Valid: {', '.join(VALID_STATES)}"
                )


def _build_handlers(client: ExpedaitClient) -> dict:
    def h_create(op, refs: RefResolver):
        payload = {
            "title": op["title"],
            "project_id": op["project_id"],
            "deliverable_type_id": op["deliverable_type_id"],
        }
        if op.get("content") is not None:
            payload["content"] = op["content"]
        if op.get("parent_deliverable_id") is not None:
            payload["parent_deliverable_id"] = op["parent_deliverable_id"]
        body = client.create_deliverable(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id}, new_id

    def h_edit(op, refs: RefResolver):
        pid = refs.resolve(op.get("id"), kind="deliverable id")
        client.update_deliverable(pid, {"content": op["content"]})
        return {"id": pid}, pid

    def h_rename(op, refs: RefResolver):
        pid = refs.resolve(op.get("id"), kind="deliverable id")
        body = client.update_deliverable(pid, {"title": op["title"]})
        return {"id": pid, "title": (body or {}).get("title")}, pid

    def h_save_version(op, refs: RefResolver):
        pid = refs.resolve(op.get("id"), kind="deliverable id")
        body = client.save_deliverable_version(pid, op.get("reason")) or {}
        return {
            "id": pid,
            "version_id": body.get("id"),
            "version_number": body.get("version_number"),
        }, pid

    def h_set_state(op, refs: RefResolver):
        pid = refs.resolve(op.get("id"), kind="deliverable id")
        body = client.set_deliverable_state(pid, op["state"], op.get("reason")) or {}
        return {"id": pid, "state": body.get("state")}, pid

    return {
        "create": h_create, "edit": h_edit, "rename": h_rename,
        "save_version": h_save_version, "set_state": h_set_state,
    }


def _run_write(ctx: click.Context, ops: list[dict]) -> None:
    """Validate, execute, and render an ops array. Shared by `write` and the
    ergonomic single-op subcommands."""
    _preflight_validate(ops)
    client = _make_client(ctx)
    try:
        results, affected = run_ops(ops, _build_handlers(client))
    finally:
        client.close()
    render_ops(ctx, results, affected, affected_key="affected_deliverable_ids")


@deliverables.command("write")
@click.option("--ops", "ops_arg", required=True, help="JSON ops array: @file.json, - (stdin), or inline.")
@click.pass_context
def write_deliverable(ctx: click.Context, ops_arg: str) -> None:
    """Apply an ordered list of write ops in one call (mirrors write_deliverable).

    Each op is one of: create, edit, rename, save_version, set_state. Chain ops
    on a freshly-created deliverable with id="$last" or bind a name on create
    (ref="x") and reference it later as id="@x".
    """
    _run_write(ctx, _load_ops(ops_arg))


@deliverables.command("create")
@click.option("--project", "--project-id", "project_id", type=int, default=None, help="Project ID (defaults to local settings).")
@click.option("--type", "--deliverable-type-id", "deliverable_type_id", type=int, required=True, help="Deliverable type ID.")
@click.option("--title", "-t", required=True, help="Deliverable title.")
@click.option("--content", default=None, help="Initial content: @file, - (stdin), or literal.")
@click.option("--parent-deliverable-id", type=int, default=None, help="Nest under this objective instance.")
@click.pass_context
def create_deliverable(
    ctx: click.Context,
    project_id: int | None,
    deliverable_type_id: int,
    title: str,
    content: str | None,
    parent_deliverable_id: int | None,
) -> None:
    """Create a new deliverable."""
    project_id = resolve_project_id(project_id)
    if project_id is None:
        raise click.UsageError(
            "No project ID given. Pass --project or run 'expedait init'."
        )
    op: dict = {
        "op": "create",
        "project_id": project_id,
        "deliverable_type_id": deliverable_type_id,
        "title": title,
    }
    if content is not None:
        op["content"] = read_value_arg(content)
    if parent_deliverable_id is not None:
        op["parent_deliverable_id"] = parent_deliverable_id
    _run_write(ctx, [op])


@deliverables.command("edit")
@click.argument("deliverable_id", type=int)
@click.option("--content", required=True, help="New content: @file, - (stdin), or literal.")
@click.pass_context
def edit_deliverable(ctx: click.Context, deliverable_id: int, content: str) -> None:
    """Replace a deliverable's content (autosave, no version bump)."""
    _run_write(ctx, [{"op": "edit", "id": deliverable_id, "content": read_value_arg(content)}])


@deliverables.command("rename")
@click.argument("deliverable_id", type=int)
@click.option("--title", "-t", required=True, help="New title.")
@click.pass_context
def rename_deliverable(ctx: click.Context, deliverable_id: int, title: str) -> None:
    """Rename a deliverable without touching its content."""
    _run_write(ctx, [{"op": "rename", "id": deliverable_id, "title": title}])


@deliverables.command("save-version")
@click.argument("deliverable_id", type=int)
@click.option("--reason", default=None, help="Optional snapshot reason / comment.")
@click.pass_context
def save_version(ctx: click.Context, deliverable_id: int, reason: str | None) -> None:
    """Save an explicit version snapshot of a deliverable."""
    op: dict = {"op": "save_version", "id": deliverable_id}
    if reason is not None:
        op["reason"] = reason
    _run_write(ctx, [op])


@deliverables.command("set-state")
@click.argument("deliverable_id", type=int)
@click.option("--state", required=True, type=click.Choice(VALID_STATES), help="Target state.")
@click.option("--reason", default=None, help="Optional transition reason / comment.")
@click.pass_context
def set_state(ctx: click.Context, deliverable_id: int, state: str, reason: str | None) -> None:
    """Transition a deliverable to a new workflow state."""
    op: dict = {"op": "set_state", "id": deliverable_id, "state": state}
    if reason is not None:
        op["reason"] = reason
    _run_write(ctx, [op])


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
