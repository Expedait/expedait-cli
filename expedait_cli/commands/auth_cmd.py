"""Auth commands: login, status, logout."""

from __future__ import annotations

import time
import webbrowser

import click
import httpx

from ..auth import resolve_api_url, resolve_token
from ..client import ExpedaitClient
from ..config import clear_config, load_config, save_config
from ..formatters import output


@click.group()
def auth() -> None:
    """Authenticate with the Expedait API."""


def _select_tenant(ctx: click.Context, memberships: list[dict]) -> int | None:
    """Prompt user to pick a tenant when multiple are available."""
    tenant_id = ctx.obj.get("tenant_id")
    if tenant_id:
        return tenant_id
    if len(memberships) == 1:
        return memberships[0]["tenant_id"]
    if len(memberships) > 1:
        click.echo("Available tenants:")
        for m in memberships:
            click.echo(f"  [{m['tenant_id']}] {m.get('tenant_name', 'Unknown')} ({m['role']})")
        return click.prompt("Select tenant ID", type=int)
    return None


def _login_password(api_url: str) -> tuple[str, dict]:
    """Interactive email/password login. Returns (token, user_info)."""
    email = click.prompt("Email")
    password = click.prompt("Password", hide_input=True)

    try:
        token_data = ExpedaitClient.login(api_url, email, password)
    except httpx.RequestError as exc:
        raise click.ClickException(f"Cannot reach {api_url}: {exc}")
    token = token_data["access_token"]

    client = ExpedaitClient(api_url, token)
    try:
        me = client.get_me()
    finally:
        client.close()
    return token, me


def _login_sso(api_url: str) -> tuple[str, dict]:
    """Browser-based SSO login via device-code-like flow. Returns (token, user_info)."""
    # Initiate CLI auth session on the server
    try:
        resp = httpx.post(f"{api_url}/api/v1/auth/cli/initiate", timeout=15.0)
    except httpx.RequestError as exc:
        raise click.ClickException(f"Cannot reach {api_url}: {exc}")
    if resp.status_code >= 400:
        raise click.ClickException(f"Failed to initiate SSO login ({resp.status_code}).")
    data = resp.json()
    session_id = data["session_id"]
    login_url = data["login_url"]

    click.echo()
    click.echo(f"Open this URL in your browser to sign in:\n")
    click.echo(f"  {login_url}")
    click.echo()

    # Try to open browser automatically
    try:
        webbrowser.open(login_url)
        click.echo("(Browser opened automatically)")
    except Exception:
        click.echo("(Could not open browser — please open the URL manually)")

    click.echo()
    click.echo("Waiting for authentication...", nl=False)

    poll_url = f"{api_url}/api/v1/auth/cli/poll/{session_id}"
    poll_interval = 2  # seconds
    max_wait = 300  # 5 minutes
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        click.echo(".", nl=False)

        try:
            poll_resp = httpx.get(poll_url, timeout=10.0)
        except httpx.RequestError:
            continue

        if poll_resp.status_code == 404:
            click.echo()
            raise click.ClickException("Login session expired. Please try again.")

        if poll_resp.status_code >= 400:
            continue

        result = poll_resp.json()
        if result["status"] == "completed":
            click.echo(" done!")
            return result["access_token"], result["user"]

    click.echo()
    raise click.ClickException("Login timed out after 5 minutes. Please try again.")


@auth.command()
@click.pass_context
def login(ctx: click.Context) -> None:
    """Login interactively via browser SSO or email/password."""
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    api_url = click.prompt("API URL", default=api_url)

    method = click.prompt(
        "Login method",
        type=click.Choice(["sso", "password"], case_sensitive=False),
        default="sso",
    )

    if method == "sso":
        token, me = _login_sso(api_url)
    else:
        token, me = _login_password(api_url)

    memberships = me.get("tenant_memberships", [])
    tenant_id = _select_tenant(ctx, memberships)

    save_config({"api_url": api_url, "token": token, "tenant_id": tenant_id})
    click.echo(f"Logged in as {me['email']} (tenant {tenant_id}).")


@auth.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current authentication status."""
    fmt = ctx.obj.get("fmt")
    try:
        token = resolve_token()
    except click.UsageError:
        click.echo("Not authenticated.")
        return

    api_url = resolve_api_url(ctx.obj.get("api_url"))
    client = ExpedaitClient(api_url, token, ctx.obj.get("tenant_id"))
    try:
        me = client.get_me()
    except click.UsageError as exc:
        click.echo(f"Token invalid: {exc}")
        return
    finally:
        client.close()

    cfg = load_config()
    info = {
        "email": me["email"],
        "user_id": me["id"],
        "tenant_id": cfg.get("tenant_id"),
        "api_url": cfg.get("api_url"),
    }
    output(info, fmt)


@auth.command()
def logout() -> None:
    """Clear stored credentials."""
    clear_config()
    click.echo("Logged out.")
