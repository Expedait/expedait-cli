"""Team commands: list, create, update, delete, write.

A *team* owns deliverable types: each deliverable type has exactly one owning
team (set with ``processes write``'s ``set_owner_team`` op). Teams are named
for what they own (Architecture, Security & Compliance), not after a job
title. Every team has one agent, and the agent's ``instructions`` are its
persona: they shape the chat, agent mode and scoring of the deliverables the
team owns. Until an owner writes some, a default applies.

Mirrors the MCP ``list_teams`` / ``write_team`` tools. The ergonomic
``create`` / ``update`` / ``delete`` subcommands each compose ``write_team``
ops and run them through the shared ops engine, so output and error handling
match ``write --ops``. Changing teams is owner-only in Expedait.
"""

from __future__ import annotations

import json

import click

from ..auth import resolve_api_url, resolve_tenant_id, resolve_token
from ..client import BackendError, ExpedaitClient
from ..formatters import is_tty, output
from ..ops import OpError, RefResolver, read_value_arg, render_ops, run_ops


TEAM_OPS_MAX = 25
VALID_TEAM_OPS = ("create_team", "update_team", "update_team_agent", "delete_team")


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)


def _preflight_validate(ops: list[dict]) -> None:
    if not ops:
        raise click.UsageError("ops must be non-empty.")
    if len(ops) > TEAM_OPS_MAX:
        raise click.UsageError(f"too many ops; max {TEAM_OPS_MAX}.")
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise click.UsageError(f"ops[{i}] must be an object.")
        op_type = op.get("op")
        if op_type not in VALID_TEAM_OPS:
            raise click.UsageError(
                f"ops[{i}].op invalid: {op_type!r}. Valid: {', '.join(VALID_TEAM_OPS)}"
            )
        if op_type == "create_team":
            ref = op.get("ref")
            if ref is not None and (not isinstance(ref, str) or not ref.strip()):
                raise click.UsageError(f"ops[{i}] (create_team): ref must be a non-empty string.")
            if op.get("name") in (None, ""):
                raise click.UsageError(f"ops[{i}] (create_team): name is required.")
            continue
        if op.get("id") in (None, ""):
            raise click.UsageError(f"ops[{i}] ({op_type}): id is required.")
        # The persona belongs to the team's agent and has its own op, so a
        # caller never believes it changed a persona it did not.
        if op_type == "update_team" and "instructions" in op:
            raise click.UsageError(
                f"ops[{i}] (update_team): instructions is not a team field; "
                "set the persona with update_team_agent(id, instructions)."
            )
        # The persona is the only thing update_team_agent writes, so an op
        # without it would silently clear it. "" is how you clear it on purpose.
        if op_type == "update_team_agent" and "instructions" not in op:
            raise click.UsageError(
                f"ops[{i}] (update_team_agent): instructions is required "
                "(pass an empty string to bring back the default)."
            )


def _put_fields(op: dict, fields) -> dict:
    return {f: op[f] for f in fields if op.get(f) is not None}


def _build_handlers(client: ExpedaitClient) -> dict:
    def h_create_team(op, refs: RefResolver):
        payload = {"name": op["name"]}
        payload.update(_put_fields(op, ("description", "instructions")))
        body = client.create_team(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_update_team(op, refs: RefResolver):
        tid = refs.resolve(op["id"], kind="team id")
        body = client.update_team(tid, _put_fields(op, ("name", "description")))
        return {"id": tid, "name": (body or {}).get("name")}, tid

    def h_update_team_agent(op, refs: RefResolver):
        tid = refs.resolve(op["id"], kind="team id")
        body = client.update_team_agent(tid, op.get("instructions"))
        return {"id": tid, "agent_id": (body or {}).get("id")}, tid

    def h_delete_team(op, refs: RefResolver):
        tid = refs.resolve(op["id"], kind="team id")
        try:
            client.delete_team(tid)
        except BackendError as exc:
            # The API refuses while deliverable types still point at the team
            # and names them; say what to do rather than relay a bare 409.
            if exc.status == 409:
                # The client has already unwrapped the API's `detail`.
                detail = exc.body.get("detail") if isinstance(exc.body, dict) else exc.body
                raise OpError(
                    "team_owns_types",
                    str(detail or "the team still owns deliverable types"),
                    fix_hint=(
                        "give those deliverable types another owning team with the "
                        "set_owner_team op of `expedait processes write`, then delete"
                    ),
                ) from exc
            raise
        return {"id": tid, "deleted": True}, tid

    return {
        "create_team": h_create_team,
        "update_team": h_update_team,
        "update_team_agent": h_update_team_agent,
        "delete_team": h_delete_team,
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
def teams() -> None:
    """Manage the workspace's teams (one owning team per deliverable type)."""


@teams.command("list")
@click.pass_context
def list_teams(ctx: click.Context) -> None:
    """List the workspace's teams."""
    client = _make_client(ctx)
    try:
        data = client.list_teams()
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
            "description": t.get("description") or "",
        }
        for t in data
    ]
    output(rows, "text")


@teams.command("create")
@click.option("--name", "-n", required=True, help="Team name: what the team owns, not a job title.")
@click.option("--description", default=None, help="Team description.")
@click.option("--instructions", default=None, help="The team agent's persona: @file, - (stdin), or literal.")
@click.pass_context
def create_team(ctx: click.Context, name: str, description: str | None, instructions: str | None) -> None:
    """Create a team and its agent."""
    op: dict = {"op": "create_team", "name": name}
    if description is not None:
        op["description"] = description
    if instructions is not None:
        op["instructions"] = read_value_arg(instructions)
    _run_write(ctx, [op])


@teams.command("update")
@click.argument("team_id", type=int)
@click.option("--name", "-n", default=None, help="New name.")
@click.option("--description", default=None, help="New description.")
@click.option("--instructions", default=None, help="New agent persona: @file, - (stdin), or literal.")
@click.pass_context
def update_team(
    ctx: click.Context, team_id: int, name: str | None,
    description: str | None, instructions: str | None,
) -> None:
    """Update a team, or its agent's persona."""
    ops: list[dict] = []
    team_op: dict = {"op": "update_team", "id": team_id}
    if name is not None:
        team_op["name"] = name
    if description is not None:
        team_op["description"] = description
    if len(team_op) > 2:
        ops.append(team_op)
    if instructions is not None:
        ops.append({"op": "update_team_agent", "id": team_id, "instructions": read_value_arg(instructions)})
    if not ops:
        raise click.UsageError("Nothing to update. Pass --name, --description, or --instructions.")
    _run_write(ctx, ops)


@teams.command("delete")
@click.argument("team_id", type=int)
@click.pass_context
def delete_team(ctx: click.Context, team_id: int) -> None:
    """Delete a team (refused while it still owns deliverable types)."""
    _run_write(ctx, [{"op": "delete_team", "id": team_id}])


@teams.command("write")
@click.option("--ops", "ops_arg", required=True, help="JSON ops array: @file.json, - (stdin), or inline.")
@click.pass_context
def write_team(ctx: click.Context, ops_arg: str) -> None:
    """Apply an ordered list of team ops in one call (mirrors write_team).

    Each op is one of: create_team, update_team, update_team_agent,
    delete_team. Chain via named refs: a create_team op carries ref="x",
    later ops reference id="@x".
    """
    raw = read_value_arg(ops_arg)
    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--ops is not valid JSON: {exc}")
    if not isinstance(ops, list):
        raise click.UsageError("--ops must be a JSON array of op objects.")
    _run_write(ctx, ops)
