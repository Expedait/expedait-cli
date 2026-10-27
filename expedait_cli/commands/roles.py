"""`roles` was replaced by `teams`.

Expedait replaced project roles with teams: each deliverable type has exactly
one owning team, and each team has an agent whose instructions are its persona.
The role endpoints no longer exist, so every `roles` command failed with an API
error that did not say why. This hidden command says where to go instead.
"""

from __future__ import annotations

import click


@click.command(
    "roles",
    hidden=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def roles() -> None:
    """Replaced by `teams`."""
    raise click.ClickException(
        "Roles were replaced by teams in Expedait: each deliverable type has one "
        "owning team. Use `expedait teams` (list, create, update, delete, write), "
        "and the set_owner_team op of `expedait processes write`."
    )
