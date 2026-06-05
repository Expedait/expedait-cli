"""Objective commands: overview.

An *objective* is a top-level deliverable that nests child deliverables beneath
it via ``parent_deliverable_id``.
"""

from __future__ import annotations

import click

from ..auth import resolve_api_url, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import output


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)


@click.group()
def objectives() -> None:
    """Navigate objectives and their descendant deliverables."""


@objectives.command("overview")
@click.argument("deliverable_id", type=int)
@click.pass_context
def overview(ctx: click.Context, deliverable_id: int) -> None:
    """Show an objective's metadata plus its full descendant tree.

    Errors if DELIVERABLE_ID is not an objective.
    """
    client = _make_client(ctx)
    try:
        data = client.get_objective_overview(deliverable_id)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json":
        output(data, "json")
        return

    click.echo(
        f"[{data.get('deliverable_id')}] {data.get('title')} "
        f"({data.get('deliverable_type_name')}) — {data.get('state')}"
    )
    descendants = data.get("descendants") or []
    if not descendants:
        click.echo("  (no descendants)")
        return
    for d in descendants:
        indent = "  " * (int(d.get("depth", 0)) + 1)
        score = d.get("score")
        score_str = f" score={score}" if score is not None else ""
        click.echo(
            f"{indent}[{d.get('id')}] {d.get('title')} "
            f"({d.get('deliverable_type_name')}) — {d.get('state')}{score_str}"
        )
