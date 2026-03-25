"""Tests for auth commands."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


class TestAuthLoginPassword:
    """Tests for the password login path."""

    def test_login_password_success(self, tmp_path: Path):
        with patch("expedait_cli.commands.auth_cmd.ExpedaitClient") as MockClient, \
             patch("expedait_cli.commands.auth_cmd.save_config") as mock_save:

            MockClient.login.return_value = {"access_token": "new-token"}
            instance = MagicMock()
            instance.get_me.return_value = {
                "id": 1,
                "email": "user@test.com",
                "tenant_memberships": [{"tenant_id": 1, "tenant_name": "T1", "role": "member"}],
            }
            MockClient.return_value = instance

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["auth", "login"],
                input="password\nuser@test.com\npass123\n",
            )

            assert result.exit_code == 0
            assert "Logged in" in result.output
            MockClient.login.assert_called_once()
            mock_save.assert_called_once()

    def test_login_password_bad_credentials(self):
        import click
        with patch("expedait_cli.commands.auth_cmd.ExpedaitClient") as MockClient:
            MockClient.login.side_effect = click.UsageError("Invalid email or password.")

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["auth", "login"],
                input="password\nbad@test.com\nwrong\n",
            )

            assert result.exit_code != 0
            assert "Invalid email" in result.output


class TestAuthLoginSSO:
    """Tests for the SSO login path."""

    def test_login_sso_success(self):
        with patch("expedait_cli.commands.auth_cmd.httpx") as mock_httpx, \
             patch("expedait_cli.commands.auth_cmd.webbrowser") as mock_wb, \
             patch("expedait_cli.commands.auth_cmd.time") as mock_time, \
             patch("expedait_cli.commands.auth_cmd.save_config") as mock_save:

            # Mock initiate response
            initiate_resp = MagicMock()
            initiate_resp.status_code = 200
            initiate_resp.json.return_value = {
                "session_id": "abc-123",
                "login_url": "https://app.expedait.org/api/v1/auth/cli/verify/abc-123",
            }
            mock_httpx.post.return_value = initiate_resp

            # Mock poll response - immediately completed
            poll_resp = MagicMock()
            poll_resp.status_code = 200
            poll_resp.json.return_value = {
                "status": "completed",
                "access_token": "sso-token",
                "user": {
                    "id": 1,
                    "email": "user@test.com",
                    "tenant_memberships": [{"tenant_id": 1, "tenant_name": "T1", "role": "member"}],
                },
            }
            mock_httpx.get.return_value = poll_resp
            mock_time.sleep = MagicMock()

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["auth", "login"],
                input="sso\n",
            )

            assert result.exit_code == 0
            assert "Logged in" in result.output
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            assert saved["token"] == "sso-token"

    def test_login_sso_initiate_failure(self):
        with patch("expedait_cli.commands.auth_cmd.httpx") as mock_httpx:

            initiate_resp = MagicMock()
            initiate_resp.status_code = 500
            mock_httpx.post.return_value = initiate_resp

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["auth", "login"],
                input="sso\n",
            )

            assert result.exit_code != 0
            assert "Failed to initiate SSO" in result.output

    def test_login_sso_session_expired(self):
        with patch("expedait_cli.commands.auth_cmd.httpx") as mock_httpx, \
             patch("expedait_cli.commands.auth_cmd.webbrowser"), \
             patch("expedait_cli.commands.auth_cmd.time") as mock_time:

            initiate_resp = MagicMock()
            initiate_resp.status_code = 200
            initiate_resp.json.return_value = {
                "session_id": "abc-123",
                "login_url": "https://example.com/verify/abc-123",
            }
            mock_httpx.post.return_value = initiate_resp

            # Poll returns 404 (expired)
            poll_resp = MagicMock()
            poll_resp.status_code = 404
            mock_httpx.get.return_value = poll_resp
            mock_time.sleep = MagicMock()

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["auth", "login"],
                input="sso\n",
            )

            assert result.exit_code != 0
            assert "expired" in result.output


class TestAuthLoginMultipleTenants:
    """Test tenant selection for both login methods."""

    def test_multiple_tenants_prompts_selection(self):
        with patch("expedait_cli.commands.auth_cmd.ExpedaitClient") as MockClient, \
             patch("expedait_cli.commands.auth_cmd.save_config") as mock_save:

            MockClient.login.return_value = {"access_token": "new-token"}
            instance = MagicMock()
            instance.get_me.return_value = {
                "id": 1,
                "email": "user@test.com",
                "tenant_memberships": [
                    {"tenant_id": 1, "tenant_name": "Tenant A", "role": "member"},
                    {"tenant_id": 2, "tenant_name": "Tenant B", "role": "owner"},
                ],
            }
            MockClient.return_value = instance

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["auth", "login"],
                input="password\nuser@test.com\npass123\n2\n",
            )

            assert result.exit_code == 0
            assert "Logged in" in result.output
            saved = mock_save.call_args[0][0]
            assert saved["tenant_id"] == 2


class TestAuthStatus:
    def test_status_authenticated(self):
        with patch("expedait_cli.commands.auth_cmd.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.auth_cmd.resolve_api_url", return_value="http://localhost:8000"), \
             patch("expedait_cli.commands.auth_cmd.load_config", return_value={"tenant_id": 1, "api_url": "http://localhost:8000"}), \
             patch("expedait_cli.commands.auth_cmd.ExpedaitClient") as MockClient:

            instance = MagicMock()
            instance.get_me.return_value = {"id": 1, "email": "user@test.com"}
            MockClient.return_value = instance

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "auth", "status"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["email"] == "user@test.com"

    def test_status_not_authenticated(self):
        import click
        with patch("expedait_cli.commands.auth_cmd.resolve_token", side_effect=click.UsageError("Not authenticated")):

            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "status"])

            assert result.exit_code == 0
            assert "Not authenticated" in result.output


class TestAuthLogout:
    def test_logout(self):
        with patch("expedait_cli.commands.auth_cmd.clear_config") as mock_clear:
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "logout"])

            assert result.exit_code == 0
            assert "Logged out" in result.output
            mock_clear.assert_called_once()
