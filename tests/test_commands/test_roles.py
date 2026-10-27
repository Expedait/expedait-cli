"""`roles` is gone: Expedait replaced project roles with teams.

The role endpoints no longer exist, so every `roles` command failed with an
API error that did not say why. The command now says where to go instead.
"""

from click.testing import CliRunner

from expedait_cli.main import cli


def test_roles_points_to_teams():
    result = CliRunner().invoke(cli, ["roles", "list"])
    assert result.exit_code != 0
    assert "expedait teams" in result.output


def test_roles_is_not_listed_in_help():
    result = CliRunner().invoke(cli, ["--help"])
    assert "roles" not in result.output
    assert "teams" in result.output
