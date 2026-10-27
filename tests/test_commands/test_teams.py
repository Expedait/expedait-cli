"""Tests for the teams commands (mirrors MCP list_teams / write_team)."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.client import BackendError
from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.teams.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.teams.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.teams.resolve_tenant_id", return_value=1),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.teams.ExpedaitClient", return_value=mock)


def _run(args, mock):
    p = _patch_auth()
    with p[0], p[1], p[2], _patch_client(mock):
        return CliRunner().invoke(cli, args)


class TestList:
    def test_json(self):
        items = [{"id": 9, "name": "Engineering", "description": "builds"}]
        mock = MagicMock(list_teams=MagicMock(return_value=items), close=MagicMock())
        result = _run(["--format", "json", "teams", "list"], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["name"] == "Engineering"


class TestErgonomic:
    def test_create(self):
        mock = MagicMock(
            create_team=MagicMock(return_value={"id": 12, "name": "Security"}), close=MagicMock(),
        )
        result = _run(
            ["--format", "json", "teams", "create", "--name", "Security",
             "--description", "signs off releases", "--instructions", "Be strict."],
            mock,
        )
        assert result.exit_code == 0
        assert json.loads(result.output)["affected_ids"] == [12]
        payload = mock.create_team.call_args.args[0]
        assert payload == {"name": "Security", "description": "signs off releases", "instructions": "Be strict."}

    def test_update_name(self):
        mock = MagicMock(
            update_team=MagicMock(return_value={"id": 12, "name": "Security & Compliance"}),
            close=MagicMock(),
        )
        result = _run(["teams", "update", "12", "--name", "Security & Compliance"], mock)
        assert result.exit_code == 0
        mock.update_team.assert_called_once_with(12, {"name": "Security & Compliance"})
        mock.update_team_agent.assert_not_called()

    def test_update_instructions_goes_to_the_team_agent(self):
        """The persona belongs to the team's agent, which has its own endpoint."""
        mock = MagicMock(
            update_team_agent=MagicMock(return_value={"id": 3, "team_id": 12}), close=MagicMock(),
        )
        result = _run(["teams", "update", "12", "--instructions", "Be strict."], mock)
        assert result.exit_code == 0
        mock.update_team_agent.assert_called_once_with(12, "Be strict.")
        mock.update_team.assert_not_called()

    def test_update_nothing_errors(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["teams", "update", "12"], mock)
        assert result.exit_code != 0
        assert "Nothing to update" in result.output

    def test_delete(self):
        mock = MagicMock(delete_team=MagicMock(return_value=None), close=MagicMock())
        result = _run(["teams", "delete", "12"], mock)
        assert result.exit_code == 0
        mock.delete_team.assert_called_once_with(12)

    def test_delete_refused_while_the_team_owns_types_says_what_to_do(self):
        # The client unwraps the API's `detail`, so the body is the message itself.
        refusal = BackendError(409, "Team owns deliverable types and cannot be deleted: Release Review")
        mock = MagicMock(delete_team=MagicMock(side_effect=refusal), close=MagicMock())
        result = _run(["--format", "json", "teams", "delete", "12"], mock)
        assert result.exit_code != 0
        op = json.loads(result.output)["ops"][0]
        assert op["error_code"] == "team_owns_types"
        assert "Release Review" in op["error"]
        assert "set_owner_team" in op["fix_hint"]


class TestWriteOps:
    def test_create_then_set_the_agent_instructions(self):
        mock = MagicMock(
            create_team=MagicMock(return_value={"id": 20, "name": "QA"}),
            update_team_agent=MagicMock(return_value={"id": 4, "team_id": 20}),
            close=MagicMock(),
        )
        ops = [
            {"op": "create_team", "ref": "q", "name": "QA"},
            {"op": "update_team_agent", "id": "@q", "instructions": "Test first."},
        ]
        result = _run(["--format", "json", "teams", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)["all_ok"] is True
        mock.update_team_agent.assert_called_once_with(20, "Test first.")

    def test_instructions_on_update_team_is_refused_before_any_write(self):
        mock = MagicMock(close=MagicMock())
        ops = [{"op": "update_team", "id": 12, "instructions": "Be strict."}]
        result = _run(["teams", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        assert "update_team_agent" in result.output
        mock.update_team.assert_not_called()

    def test_update_team_agent_without_instructions_is_refused(self):
        mock = MagicMock(close=MagicMock())
        ops = [{"op": "update_team_agent", "id": 12}]
        result = _run(["teams", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        assert "instructions is required" in result.output
        mock.update_team_agent.assert_not_called()

    def test_role_ops_are_refused(self):
        mock = MagicMock(close=MagicMock())
        ops = [{"op": "create_role", "name": "PM"}]
        result = _run(["teams", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        assert "create_team" in result.output
