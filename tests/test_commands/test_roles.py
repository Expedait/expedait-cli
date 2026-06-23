"""Tests for the roles commands (mirrors MCP list_roles / write_role)."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.roles.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.roles.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.roles.resolve_tenant_id", return_value=1),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.roles.ExpedaitClient", return_value=mock)


def _run(args, mock):
    p = _patch_auth()
    with p[0], p[1], p[2], _patch_client(mock):
        return CliRunner().invoke(cli, args)


class TestList:
    def test_json(self):
        items = [{"id": 9, "name": "Engineer", "description": "builds"}]
        mock = MagicMock(list_roles=MagicMock(return_value=items), close=MagicMock())
        result = _run(["--format", "json", "roles", "list"], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["name"] == "Engineer"


class TestErgonomic:
    def test_create(self):
        mock = MagicMock(
            create_role=MagicMock(return_value={"id": 12, "name": "PM"}), close=MagicMock(),
        )
        result = _run(
            ["--format", "json", "roles", "create", "--name", "PM",
             "--description", "owns roadmap", "--instructions", "Be concise."],
            mock,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["affected_ids"] == [12]
        payload = mock.create_role.call_args.args[0]
        assert payload == {"name": "PM", "description": "owns roadmap", "instructions": "Be concise."}

    def test_update(self):
        mock = MagicMock(
            update_role=MagicMock(return_value={"id": 12, "name": "Lead PM"}), close=MagicMock(),
        )
        result = _run(["roles", "update", "12", "--name", "Lead PM"], mock)
        assert result.exit_code == 0
        mock.update_role.assert_called_once_with(12, {"name": "Lead PM"})

    def test_update_nothing_errors(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["roles", "update", "12"], mock)
        assert result.exit_code != 0
        assert "Nothing to update" in result.output

    def test_delete(self):
        mock = MagicMock(delete_role=MagicMock(return_value=None), close=MagicMock())
        result = _run(["roles", "delete", "12"], mock)
        assert result.exit_code == 0
        mock.delete_role.assert_called_once_with(12)


class TestWriteOps:
    def test_multi_op(self):
        mock = MagicMock(
            create_role=MagicMock(return_value={"id": 20, "name": "QA"}),
            update_role=MagicMock(return_value={"id": 20, "name": "QA Lead"}),
            close=MagicMock(),
        )
        ops = [
            {"op": "create_role", "ref": "q", "name": "QA"},
            {"op": "update_role", "id": "@q", "name": "QA Lead"},
        ]
        result = _run(["--format", "json", "roles", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_ok"] is True
        mock.update_role.assert_called_once_with(20, {"name": "QA Lead"})
