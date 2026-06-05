"""Tests for context commands."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.context_cmd.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.context_cmd.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.context_cmd.resolve_tenant_id", return_value=1),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.context_cmd.ExpedaitClient", return_value=mock)


class TestContextGet:
    def test_get(self):
        ctx = {"deliverable_id": 1, "dependencies": [], "sources": [], "total_chars": 1234}
        mock = MagicMock(get_deliverable_context=MagicMock(return_value=ctx), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "context", "get", "1"])
            assert result.exit_code == 0
            assert json.loads(result.output)["total_chars"] == 1234
            mock.get_deliverable_context.assert_called_once_with(1)
