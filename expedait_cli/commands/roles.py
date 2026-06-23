"""Role commands: list, create, update, delete, write.

A *role* is a workspace project role — the owner-role pool an agent assigns to
deliverable types (via ``processes write``'s ``set_owner_roles`` op). A role's
``instructions`` is its LLM coaching persona (the system prompt for
deliverables this role owns).

Mirrors the MCP ``list_roles`` / ``write_role`` tools. The ergonomic
``create`` / ``update`` / ``delete`` subcommands each compose a single
``write_role`` op and run it through the shared ops engine, so output and error
handling match ``write --ops``.
"""

from __future__ import annotations

import json

import click

from ..auth import resolve_api_url, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import is_tty, output
from ..ops import RefResolver, read_value_arg, render_ops, run_ops


ROLE_OPS_MAX = 25
VALID_ROLE_OPS = ("create_role", "update_role", "delete_role")


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)




def _preflight_validate(ops: list[dict]) -> None:
    if not ops:
        raise click.UsageError("ops must be non-empty.")
    if len(ops) > ROLE_OPS_MAX:
        raise click.UsageError(f"too many ops; max {ROLE_OPS_MAX}.")
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise click.UsageError(f"ops[{i}] must be an object.")
        op_type = op.get("op")
        if op_type not in VALID_ROLE_OPS:
            raise click.UsageError(
                f"ops[{i}].op invalid: {op_type!r}. Valid: {', '.join(VALID_ROLE_OPS)}"
            )
        ref = op.get("ref")
        if op_type == "create_role" and ref is not None:
            if not isinstance(ref, str) or not ref.strip():
                raise click.UsageError(f"ops[{i}] (create_role): ref must be a non-empty string.")
        if op_type == "create_role":
            if op.get("name") in (None, ""):
                raise click.UsageError(f"ops[{i}] (create_role): name is required.")
        else:
            if op.get("id") in (None, ""):
                raise click.UsageError(f"ops[{i}] ({op_type}): id is required.")


def _put_fields(op: dict, fields) -> dict:
    return {f: op[f] for f in fields if op.get(f) is not None}


def _build_handlers(client: ExpedaitClient) -> dict:
    def h_create_role(op, refs: RefResolver):
        payload = {"name": op["name"]}
        payload.update(_put_fields(op, ("description", "instructions")))
        body = client.create_role(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_update_role(op, refs: RefResolver):
        rid = refs.resolve(op["id"], kind="role id")
        body = client.update_role(rid, _put_fields(op, ("name", "description", "instructions")))
        return {"id": rid, "name": (body or {}).get("name")}, rid

    def h_delete_role(op, refs: RefResolver):
        rid = refs.resolve(op["id"], kind="role id")
        client.delete_role(rid)
        return {"id": rid, "deleted": True}, rid

    return {
        "create_role": h_create_role,
        "update_role": h_update_role,
        "delete_role": h_delete_role,
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
def roles() -> None:
    """Manage the workspace's project roles (owner-role pool)."""


@roles.command("list")
@click.pass_context
def list_roles(ctx: click.Context) -> None:
    """List the workspace's project roles."""
    client = _make_client(ctx)
    try:
        data = client.list_roles()
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(data, "json")
        return
    rows = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "description": r.get("description") or "",
        }
        for r in data
    ]
    output(rows, "text")


@roles.command("create")
@click.option("--name", "-n", required=True, help="Role name.")
@click.option("--description", default=None, help="Role description.")
@click.option("--instructions", default=None, help="LLM coaching persona: @file, - (stdin), or literal.")
@click.pass_context
def create_role(ctx: click.Context, name: str, description: str | None, instructions: str | None) -> None:
    """Create a new project role."""
    op: dict = {"op": "create_role", "name": name}
    if description is not None:
        op["description"] = description
    if instructions is not None:
        op["instructions"] = read_value_arg(instructions)
    _run_write(ctx, [op])


@roles.command("update")
@click.argument("role_id", type=int)
@click.option("--name", "-n", default=None, help="New name.")
@click.option("--description", default=None, help="New description.")
@click.option("--instructions", default=None, help="New LLM coaching persona: @file, - (stdin), or literal.")
@click.pass_context
def update_role(
    ctx: click.Context, role_id: int, name: str | None,
    description: str | None, instructions: str | None,
) -> None:
    """Update a project role."""
    op: dict = {"op": "update_role", "id": role_id}
    if name is not None:
        op["name"] = name
    if description is not None:
        op["description"] = description
    if instructions is not None:
        op["instructions"] = read_value_arg(instructions)
    if len(op) == 2:
        raise click.UsageError("Nothing to update. Pass --name, --description, or --instructions.")
    _run_write(ctx, [op])


@roles.command("delete")
@click.argument("role_id", type=int)
@click.pass_context
def delete_role(ctx: click.Context, role_id: int) -> None:
    """Delete a project role."""
    _run_write(ctx, [{"op": "delete_role", "id": role_id}])


@roles.command("write")
@click.option("--ops", "ops_arg", required=True, help="JSON ops array: @file.json, - (stdin), or inline.")
@click.pass_context
def write_role(ctx: click.Context, ops_arg: str) -> None:
    """Apply an ordered list of role ops in one call (mirrors write_role).

    Each op is one of: create_role, update_role, delete_role. Chain via named
    refs: a create_role op carries ref="x", later ops reference id="@x".
    """
    raw = read_value_arg(ops_arg)
    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--ops is not valid JSON: {exc}")
    if not isinstance(ops, list):
        raise click.UsageError("--ops must be a JSON array of op objects.")
    _run_write(ctx, ops)
