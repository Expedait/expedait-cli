"""Expedait CLI entry point."""

from __future__ import annotations

import click

from . import __version__
from .commands.auth_cmd import auth
from .commands.init_cmd import init
from .commands.projects import projects
from .commands.deliverables import deliverables, pages
from .commands.objectives import objectives
from .commands.context_cmd import context
from .commands.review import review
from .commands.comments import comments


@click.group()
@click.option("--api-url", envvar="EXPEDAIT_API_URL", default=None, help="API base URL.")
@click.option("--tenant-id", envvar="EXPEDAIT_TENANT_ID", type=int, default=None, help="Tenant ID.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default=None, help="Output format.")
@click.version_option(__version__)
@click.pass_context
def cli(ctx: click.Context, api_url: str | None, tenant_id: int | None, fmt: str | None) -> None:
    """Expedait CLI — download project specs, post comments."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url
    ctx.obj["tenant_id"] = tenant_id
    ctx.obj["fmt"] = fmt


cli.add_command(auth)
cli.add_command(init)
cli.add_command(projects)
cli.add_command(deliverables)
cli.add_command(objectives)
cli.add_command(context)
cli.add_command(review)
cli.add_command(comments)
# Deprecated alias — warns and forwards to `deliverables`. Drop next release.
cli.add_command(pages)
