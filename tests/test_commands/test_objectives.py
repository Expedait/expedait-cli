"""Tests for objectives commands."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.objectives.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.objectives.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.objectives.resolve_tenant_id", return_value=1),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.objectives.ExpedaitClient", return_value=mock)


class TestObjectivesOverview:
    def test_text_tree(self):
        overview = {
            "deliverable_id": 1, "deliverable_type_id": 3, "deliverable_type_name": "Objective",
            "title": "Launch", "state": "In Progress",
            "descendants": [
                {"id": 2, "title": "Child A", "state": "Approved", "deliverable_type_name": "Spec", "depth": 0, "score": 90},
                {"id": 3, "title": "Grandchild", "state": "Not Started", "deliverable_type_name": "Spec", "depth": 1},
            ],
        }
        mock = MagicMock(get_objective_overview=MagicMock(return_value=overview), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["objectives", "overview", "1"])
            assert result.exit_code == 0
            assert "Launch" in result.output
            assert "Child A" in result.output
            assert "Grandchild" in result.output

    def test_json(self):
        overview = {"deliverable_id": 1, "title": "Launch", "descendants": []}
        mock = MagicMock(get_objective_overview=MagicMock(return_value=overview), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "objectives", "overview", "1"])
            assert result.exit_code == 0
            assert json.loads(result.output)["title"] == "Launch"
