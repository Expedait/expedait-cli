"""Project commands: list, get, workspace, download, create, update, delete, write.

A *project* is one instantiation of a process (project type): the concrete
workspace whose deliverables an agent authors. Mirrors the MCP ``write_project``
tool. The ergonomic ``create`` / ``update`` / ``delete`` subcommands each compose
a single ``write_project`` op and run it through the shared ops engine, so output
and error handling match ``write --ops``.

Deleting a project cascades to **every** deliverable, version, file, comment, and
agent run beneath it and cannot be undone. The REST endpoint deletes immediately
with no server-side guard, so the CLI enforces a two-step confirm itself: a bare
``delete`` prints a preview and touches nothing; ``delete --confirm`` (or the
``delete_project`` op carrying ``"confirm": true``) actually deletes.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import click

from ..auth import resolve_api_url, resolve_project_id, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import output
from ..ops import OpError, RefResolver, read_value_arg, render_ops, run_ops


PROJECT_OPS_MAX = 25
VALID_PROJECT_OPS = ("create_project", "update_project", "delete_project")


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)


def _preflight_validate(ops: list[dict]) -> None:
    if not ops:
        raise click.UsageError("ops must be non-empty.")
    if len(ops) > PROJECT_OPS_MAX:
        raise click.UsageError(f"too many ops; max {PROJECT_OPS_MAX}.")
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise click.UsageError(f"ops[{i}] must be an object.")
        op_type = op.get("op")
        if op_type not in VALID_PROJECT_OPS:
            raise click.UsageError(
                f"ops[{i}].op invalid: {op_type!r}. Valid: {', '.join(VALID_PROJECT_OPS)}"
            )
        if op_type == "create_project":
            ref = op.get("ref")
            if ref is not None and (not isinstance(ref, str) or not ref.strip()):
                raise click.UsageError(f"ops[{i}] (create_project): ref must be a non-empty string.")
            if op.get("name") in (None, ""):
                raise click.UsageError(f"ops[{i}] (create_project): name is required.")
            if op.get("project_type_id") in (None, ""):
                raise click.UsageError(
                    f"ops[{i}] (create_project): project_type_id is required."
                )
        else:
            if op.get("id") in (None, ""):
                raise click.UsageError(f"ops[{i}] ({op_type}): id is required.")


def _put_fields(op: dict, fields) -> dict:
    return {f: op[f] for f in fields if op.get(f) is not None}


def _build_handlers(client: ExpedaitClient) -> dict:
    def h_create_project(op, refs: RefResolver):
        payload = {"name": op["name"], "project_type_id": op["project_type_id"]}
        payload.update(_put_fields(op, ("description",)))
        body = client.create_project(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_update_project(op, refs: RefResolver):
        pid = refs.resolve(op["id"], kind="project id")
        body = client.update_project(
            pid, _put_fields(op, ("name", "description", "project_type_id", "repo_url")),
        )
        return {"id": pid, "name": (body or {}).get("name")}, pid

    def h_delete_project(op, refs: RefResolver):
        pid = refs.resolve(op["id"], kind="project id")
        if op.get("confirm") is not True:
            raise OpError(
                "confirm_required",
                "deleting a project cascades to all its deliverables, versions, "
                "files, comments, and agent runs and cannot be undone",
                fix_hint='re-run this op with "confirm": true',
            )
        client.delete_project(pid)
        return {"id": pid, "deleted": True}, pid

    return {
        "create_project": h_create_project,
        "update_project": h_update_project,
        "delete_project": h_delete_project,
    }


def _run_write(ctx: click.Context, ops: list[dict]) -> None:
    _preflight_validate(ops)
    client = _make_client(ctx)
    try:
        results, affected = run_ops(ops, _build_handlers(client))
    finally:
        client.close()
    render_ops(ctx, results, affected, affected_key="affected_ids")


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
@click.pass_context
def download_project(ctx: click.Context, project_id: int | None, output_dir: str) -> None:
    """Download all project deliverables as a ZIP (markdown + images) and extract."""
    project_id = resolve_project_id(project_id)
    if project_id is None:
        raise click.UsageError(
            "No project ID given. Pass PROJECT_ID or run 'expedait init'."
        )
    client = _make_client(ctx)
    try:
        data = client.download_project(project_id)
    finally:
        client.close()

    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)

    click.echo(f"Extracted to {dest.resolve()}")


@projects.command("create")
@click.option("--name", "-n", required=True, help="Project name.")
@click.option(
    "--process-id", "project_type_id", type=int, required=True,
    help="Process (project type) to instantiate from. See 'expedait processes list'.",
)
@click.option("--description", default=None, help="Project description.")
@click.pass_context
def create_project(
    ctx: click.Context, name: str, project_type_id: int, description: str | None,
) -> None:
    """Create a new project from a process (mirrors write_project's create op)."""
    op: dict = {"op": "create_project", "name": name, "project_type_id": project_type_id}
    if description is not None:
        op["description"] = description
    _run_write(ctx, [op])


@projects.command("update")
@click.argument("project_id", type=int)
@click.option("--name", "-n", default=None, help="New name.")
@click.option("--description", default=None, help="New description.")
@click.option("--process-id", "project_type_id", type=int, default=None, help="Move to a different process (project type).")
@click.option("--repo-url", default=None, help="Linked repository URL.")
@click.pass_context
def update_project(
    ctx: click.Context, project_id: int, name: str | None,
    description: str | None, project_type_id: int | None, repo_url: str | None,
) -> None:
    """Update a project's name, description, process, or repo URL."""
    op: dict = {"op": "update_project", "id": project_id}
    if name is not None:
        op["name"] = name
    if description is not None:
        op["description"] = description
    if project_type_id is not None:
        op["project_type_id"] = project_type_id
    if repo_url is not None:
        op["repo_url"] = repo_url
    if len(op) == 2:
        raise click.UsageError(
            "Nothing to update. Pass --name, --description, --process-id, or --repo-url."
        )
    _run_write(ctx, [op])


@projects.command("delete")
@click.argument("project_id", type=int)
@click.option(
    "--confirm", is_flag=True, default=False,
    help="Actually delete. Without it, this only previews the cascade.",
)
@click.pass_context
def delete_project(ctx: click.Context, project_id: int, confirm: bool) -> None:
    """Delete a project and everything under it (two-step; requires --confirm).

    A bare 'delete PROJECT_ID' fetches the project and prints what would be
    destroyed without touching anything. Re-run with --confirm to delete. The
    cascade (deliverables, versions, files, comments, agent runs) is
    irreversible.
    """
    if not confirm:
        client = _make_client(ctx)
        try:
            project = client.get_project(project_id)
        finally:
            client.close()
        name = (project or {}).get("name", f"#{project_id}")
        click.echo(
            f"Would delete project {project_id} ({name}) and ALL its deliverables, "
            "versions, files, comments, and agent runs. This cannot be undone.\n"
            f"Nothing was deleted. Re-run with --confirm to proceed:\n"
            f"    expedait projects delete {project_id} --confirm"
        )
        return
    _run_write(ctx, [{"op": "delete_project", "id": project_id, "confirm": True}])


@projects.command("write")
@click.option("--ops", "ops_arg", required=True, help="JSON ops array: @file.json, - (stdin), or inline.")
@click.pass_context
def write_project(ctx: click.Context, ops_arg: str) -> None:
    """Apply an ordered list of project ops in one call (mirrors write_project).

    Each op is one of: create_project, update_project, delete_project. Chain via
    named refs: a create_project op carries ref="x", later ops reference id="@x".
    A delete_project op must carry "confirm": true — the cascade is irreversible.
    """
    raw = read_value_arg(ops_arg)
    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--ops is not valid JSON: {exc}")
    if not isinstance(ops, list):
        raise click.UsageError("--ops must be a JSON array of op objects.")
    _run_write(ctx, ops)


def _is_tty() -> bool:
    import sys
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
