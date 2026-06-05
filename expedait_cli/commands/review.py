"""Review commands: list scoring findings and mute them.

Review issues are the actionable findings raised by the scoring/review pass on
a deliverable (severity, description, the criteria that flagged them, anchor
offsets, an optional cross-deliverable reference).
"""

from __future__ import annotations

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
def review() -> None:
    """Inspect and manage deliverable review findings."""


@review.command("issues")
@click.argument("deliverable_id", type=int)
@click.option(
    "--state",
    type=click.Choice(["open", "muted", "all"]),
    default="all",
    help="Filter by issue state (default: all).",
)
@click.pass_context
def issues(ctx: click.Context, deliverable_id: int, state: str) -> None:
    """List scoring findings raised on a deliverable."""
    client = _make_client(ctx)
    try:
        data = client.list_review_issues(deliverable_id, state=state)
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(data, "json")
        return

    if not data:
        click.echo("No review issues.")
        return
    rows = []
    for issue in data:
        anchor = issue.get("anchor") or {}
        criteria = ", ".join(c.get("display_name", "") for c in issue.get("criteria") or [])
        rows.append({
            "id": issue.get("id"),
            "severity": issue.get("severity", ""),
            "state": issue.get("state", ""),
            "criteria": criteria,
            "offsets": f"{anchor.get('start_offset', '')}-{anchor.get('end_offset', '')}",
            "description": issue.get("description", ""),
        })
    output(rows, "text")


@review.command("mute")
@click.argument("issue_id", type=int)
@click.option("--note", default=None, help="Reason for muting.")
@click.option("--unmute", is_flag=True, default=False, help="Unmute instead of mute.")
@click.pass_context
def mute(ctx: click.Context, issue_id: int, note: str | None, unmute: bool) -> None:
    """Mute (or, with --unmute, unmute) a review finding."""
    client = _make_client(ctx)
    try:
        data = client.mute_review_issue(issue_id, muted=not unmute, note=note)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))
