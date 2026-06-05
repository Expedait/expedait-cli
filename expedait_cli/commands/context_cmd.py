"""Context command: get the assembled LLM context for a deliverable.

This is the read-only context *snapshot* fed to the LLM for one deliverable
(dependency deliverables, linked external sources, uploaded files, aggregate
sizes). It is distinct from ``projects download``, which is the whole-project
on-disk spec snapshot.
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
