"""Comment commands: list, create, resolve, delete."""

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
def comments() -> None:
    """Manage page comments."""


@comments.command("list")
@click.argument("page_id", type=int)
@click.pass_context
def list_comments(ctx: click.Context, page_id: int) -> None:
    """List comments on a page."""
    client = _make_client(ctx)
    try:
        data = client.list_comments(page_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@comments.command("create")
@click.argument("page_id", type=int)
@click.option("--text", required=True, help="Comment content.")
@click.option("--selected-text", required=True, help="The text being commented on.")
@click.option("--start-offset", required=True, type=int, help="Start character offset.")
@click.option("--end-offset", required=True, type=int, help="End character offset.")
@click.option("--source-page-id", type=int, default=None, help="Agent's source page ID.")
@click.option("--parent-comment-id", type=int, default=None, help="Reply to comment ID.")
@click.pass_context
def create_comment(
    ctx: click.Context,
    page_id: int,
    text: str,
    selected_text: str,
    start_offset: int,
    end_offset: int,
    source_page_id: int | None,
    parent_comment_id: int | None,
) -> None:
    """Create a comment on a page."""
    payload: dict = {
        "comment_text": text,
        "selected_text": selected_text,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "is_agent_comment": True,
    }
    if source_page_id is not None:
        payload["source_page_id"] = source_page_id
    if parent_comment_id is not None:
        payload["parent_comment_id"] = parent_comment_id

    client = _make_client(ctx)
    try:
        data = client.create_comment(page_id, payload)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@comments.command("resolve")
@click.argument("page_id", type=int)
@click.argument("comment_id", type=int)
@click.pass_context
def resolve_comment(ctx: click.Context, page_id: int, comment_id: int) -> None:
    """Mark a comment as resolved."""
    client = _make_client(ctx)
    try:
        data = client.resolve_comment(comment_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@comments.command("delete")
@click.argument("page_id", type=int)
@click.argument("comment_id", type=int)
@click.pass_context
def delete_comment(ctx: click.Context, page_id: int, comment_id: int) -> None:
    """Delete a comment."""
    client = _make_client(ctx)
    try:
        data = client.delete_comment(comment_id)
    finally:
        client.close()
    click.echo("Comment deleted.")
