"""Tests for the init command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from expedait_cli.main import cli


def _mock_client(me_response, projects_response):
    """Return a mock ExpedaitClient class that returns given responses."""
    instance = MagicMock()
    instance.get_me.return_value = me_response
    instance.list_projects.return_value = projects_response
    instance.close = MagicMock()
    return MagicMock(return_value=instance)


ME_SINGLE_TENANT = {
    "id": 1,
    "email": "dev@test.com",
    "tenant_memberships": [
        {"tenant_id": 10, "tenant_name": "Acme Corp", "role": "admin"},
    ],
}

ME_MULTI_TENANT = {
    "id": 1,
    "email": "dev@test.com",
    "tenant_memberships": [
        {"tenant_id": 10, "tenant_name": "Acme Corp", "role": "admin"},
        {"tenant_id": 20, "tenant_name": "Other Inc", "role": "member"},
    ],
}

PROJECTS = [
    {"id": 1, "name": "Project Alpha"},
    {"id": 2, "name": "Project Beta"},
]


class TestInit:
    def test_single_tenant_single_project(self, tmp_path: Path):
        """Auto-selects tenant and project when only one of each."""
        mock_cls = _mock_client(ME_SINGLE_TENANT, [PROJECTS[0]])
        settings_file = tmp_path / ".expedait" / "settings.json"

        with patch("expedait_cli.commands.init_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.init_cmd.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.init_cmd.ExpedaitClient", mock_cls), \
             patch("expedait_cli.commands.init_cmd.save_settings") as mock_save:

            runner = CliRunner()
            result = runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert "Project Alpha" in result.output
            mock_save.assert_called_once_with({
                "tenant_id": 10,
                "project_id": 1,
            })

    def test_multi_tenant_prompts(self, tmp_path: Path):
        """Prompts for tenant selection when multiple are available."""
        mock_cls = _mock_client(ME_MULTI_TENANT, [PROJECTS[0]])

        with patch("expedait_cli.commands.init_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.init_cmd.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.init_cmd.ExpedaitClient", mock_cls), \
             patch("expedait_cli.commands.init_cmd.save_settings") as mock_save:

            runner = CliRunner()
            result = runner.invoke(cli, ["init"], input="10\n")

            assert result.exit_code == 0
            assert "Acme Corp" in result.output
            assert "Other Inc" in result.output
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            assert saved["tenant_id"] == 10

    def test_multi_project_prompts(self, tmp_path: Path):
        """Prompts for project selection when multiple are available."""
        mock_cls = _mock_client(ME_SINGLE_TENANT, PROJECTS)

        with patch("expedait_cli.commands.init_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.init_cmd.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.init_cmd.ExpedaitClient", mock_cls), \
             patch("expedait_cli.commands.init_cmd.save_settings") as mock_save:

            runner = CliRunner()
            result = runner.invoke(cli, ["init"], input="2\n")

            assert result.exit_code == 0
            assert "Project Alpha" in result.output
            assert "Project Beta" in result.output
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            assert saved["project_id"] == 2

    def test_explicit_tenant_id_skips_prompt(self):
        """--tenant-id flag bypasses tenant selection."""
        mock_cls = _mock_client(ME_MULTI_TENANT, [PROJECTS[0]])

        with patch("expedait_cli.commands.init_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.init_cmd.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.init_cmd.ExpedaitClient", mock_cls), \
             patch("expedait_cli.commands.init_cmd.save_settings") as mock_save:

            runner = CliRunner()
            result = runner.invoke(cli, ["--tenant-id", "20", "init"])

            assert result.exit_code == 0
            # Should not show tenant selection prompt
            assert "Select tenant" not in result.output
            saved = mock_save.call_args[0][0]
            assert saved["tenant_id"] == 20

    def test_not_authenticated_fails(self):
        """Fails gracefully when not logged in."""
        import click
        with patch("expedait_cli.commands.init_cmd.resolve_token",
                    side_effect=click.UsageError("Not authenticated")):

            runner = CliRunner()
            result = runner.invoke(cli, ["init"])

            assert result.exit_code != 0
            assert "Not authenticated" in result.output

    def test_no_projects_fails(self):
        """Fails when tenant has no projects."""
        mock_cls = _mock_client(ME_SINGLE_TENANT, [])

        with patch("expedait_cli.commands.init_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.init_cmd.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.init_cmd.ExpedaitClient", mock_cls):

            runner = CliRunner()
            result = runner.invoke(cli, ["init"])

            assert result.exit_code != 0
            assert "No projects found" in result.output

    def test_invalid_project_id_fails(self):
        """Fails when user enters a project ID not in the list."""
        mock_cls = _mock_client(ME_SINGLE_TENANT, PROJECTS)

        with patch("expedait_cli.commands.init_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.init_cmd.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.init_cmd.ExpedaitClient", mock_cls):

            runner = CliRunner()
            result = runner.invoke(cli, ["init"], input="999\n")

            assert result.exit_code != 0
            assert "not found" in result.output
