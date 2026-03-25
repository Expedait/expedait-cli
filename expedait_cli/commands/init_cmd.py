"""Init command: configure project-local settings."""

from __future__ import annotations

import click

from ..auth import resolve_api_url, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..settings import save_settings


@click.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize Expedait settings for this project directory.

    Requires authentication. Prompts for tenant and project selection,
    then writes .expedait/settings.json in the current directory.
    """
    # Verify auth
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))

    client = ExpedaitClient(api_url, token)
    try:
        me = client.get_me()
    except click.UsageError:
        raise click.UsageError(
            "Authentication failed. Run 'expedait auth login' first."
        )

    # Select tenant
    memberships = me.get("tenant_memberships", [])
    explicit_tenant = ctx.obj.get("tenant_id")

    if explicit_tenant is not None:
        tenant_id = explicit_tenant
    elif len(memberships) == 1:
        tenant_id = memberships[0]["tenant_id"]
        click.echo(f"Using tenant: {memberships[0].get('tenant_name', tenant_id)}")
    elif len(memberships) > 1:
        click.echo("Available tenants:")
        for m in memberships:
            click.echo(f"  [{m['tenant_id']}] {m.get('tenant_name', 'Unknown')} ({m['role']})")
        tenant_id = click.prompt("Select tenant ID", type=int)
    else:
        raise click.UsageError("No tenant memberships found for this user.")

    # Fetch projects for selected tenant
    tenant_client = ExpedaitClient(api_url, token, tenant_id)
    try:
        projects = tenant_client.list_projects()
    finally:
        tenant_client.close()

    if not projects:
        raise click.UsageError("No projects found in this tenant.")

    if len(projects) == 1:
        project = projects[0]
        click.echo(f"Using project: {project['name']}")
    else:
        click.echo("Available projects:")
        for p in projects:
            click.echo(f"  [{p['id']}] {p['name']}")
        project_id = click.prompt("Select project ID", type=int)
        project = next((p for p in projects if p["id"] == project_id), None)
        if project is None:
            raise click.UsageError(f"Project {project_id} not found in list.")

    save_settings({
        "tenant_id": tenant_id,
        "project_id": project["id"],
    })

    click.echo(f"Saved .expedait/settings.json (tenant={tenant_id}, project={project['id']}).")
    client.close()
