"""Tests for the processes commands (mirrors MCP list/get/write_process)."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.processes.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.processes.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.processes.resolve_tenant_id", return_value=1),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.processes.ExpedaitClient", return_value=mock)


def _run(args, mock):
    p = _patch_auth()
    with p[0], p[1], p[2], _patch_client(mock):
        return CliRunner().invoke(cli, args)


class TestList:
    def test_json(self):
        items = [{"id": 1, "name": "Product Dev", "description": "d", "icon": "🚀"}]
        mock = MagicMock(list_processes=MagicMock(return_value=items), close=MagicMock())
        result = _run(["--format", "json", "processes", "list"], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["name"] == "Product Dev"


class TestGet:
    def test_assembles_tree(self):
        mock = MagicMock(
            get_process_type=MagicMock(return_value={"id": 1, "name": "P", "description": "d", "icon": "x"}),
            get_process_phases=MagicMock(return_value=[
                {"id": 10, "name": "Discovery", "order": 1, "project_type_id": 1},
            ]),
            get_process_rows=MagicMock(return_value=[{"id": 100, "phase_id": 10, "position": 1000.0}]),
            list_roles=MagicMock(return_value=[{"id": 9, "name": "Engineer"}]),
            list_deliverable_types=MagicMock(return_value=[
                {"id": 50, "name": "Spec", "phase_id": 10, "col_position": 1000.0,
                 "owner_role_ids": [9], "dependency_ids": []},
            ]),
            close=MagicMock(),
        )
        result = _run(["--format", "json", "processes", "get", "1"], mock)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["process"]["name"] == "P"
        phase = data["phases"][0]
        assert phase["name"] == "Discovery"
        card = phase["deliverable_types"][0]
        assert card["name"] == "Spec"
        assert card["owner_roles"][0]["name"] == "Engineer"


class TestWrite:
    def test_create_type_auto_places_col(self):
        mock = MagicMock(
            list_deliverable_types=MagicMock(return_value=[]),  # empty -> col 1000
            create_deliverable_type=MagicMock(return_value={"id": 50, "name": "A"}),
            close=MagicMock(),
        )
        ops = [{"op": "create_deliverable_type", "phase_id": 10, "name": "A"}]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        payload = mock.create_deliverable_type.call_args.args[0]
        assert payload["col_position"] == 1000.0
        assert payload["phase_id"] == 10

    def test_named_refs_chain(self):
        mock = MagicMock(
            create_process=MagicMock(return_value={"id": 1, "name": "P"}),
            create_phase=MagicMock(return_value={"id": 10, "name": "Ph"}),
            list_deliverable_types=MagicMock(return_value=[]),
            create_deliverable_type=MagicMock(return_value={"id": 50, "name": "A"}),
            close=MagicMock(),
        )
        ops = [
            {"op": "create_process", "ref": "p", "name": "P"},
            {"op": "create_phase", "ref": "ph", "process_id": "@p", "name": "Ph"},
            {"op": "create_deliverable_type", "ref": "a", "phase_id": "@ph", "name": "A"},
        ]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_ok"] is True
        # create_phase resolved @p -> 1
        assert mock.create_phase.call_args.args[0]["project_type_id"] == 1
        # create_deliverable_type resolved @ph -> 10
        assert mock.create_deliverable_type.call_args.args[0]["phase_id"] == 10

    def test_set_owner_roles_by_name(self):
        mock = MagicMock(
            list_roles=MagicMock(return_value=[{"id": 9, "name": "Engineer"}]),
            set_deliverable_type_owner_roles=MagicMock(return_value=None),
            close=MagicMock(),
        )
        ops = [{"op": "set_owner_roles", "type_id": 50, "role_names": ["Engineer"]}]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        mock.set_deliverable_type_owner_roles.assert_called_once_with(50, [9])

    def test_set_owner_roles_unknown_name_errors(self):
        mock = MagicMock(
            list_roles=MagicMock(return_value=[{"id": 9, "name": "Engineer"}]),
            set_deliverable_type_owner_roles=MagicMock(return_value=None),
            close=MagicMock(),
        )
        ops = [{"op": "set_owner_roles", "type_id": 50, "role_names": ["Ghost"]}]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ops"][0]["error_code"] == "unknown_role"
        mock.set_deliverable_type_owner_roles.assert_not_called()

    def test_delete_process_in_use_guard(self):
        mock = MagicMock(
            list_projects=MagicMock(return_value=[{"id": 1, "project_type_id": 3}]),
            delete_process=MagicMock(),
            close=MagicMock(),
        )
        ops = [{"op": "delete_process", "id": 3}]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ops"][0]["error_code"] == "delete_in_use"
        mock.delete_process.assert_not_called()

    def test_delete_process_confirmed(self):
        mock = MagicMock(
            list_projects=MagicMock(return_value=[{"id": 1, "project_type_id": 3}]),
            delete_process=MagicMock(return_value=None),
            close=MagicMock(),
        )
        ops = [{"op": "delete_process", "id": 3, "confirm_in_use": True}]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        mock.delete_process.assert_called_once_with(3)

    def test_preflight_phase_xor(self):
        mock = MagicMock(close=MagicMock())
        ops = [{"op": "create_phase", "name": "P", "process_id": 1, "parent_type_id": 2}]
        result = _run(["processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        assert "exactly one" in result.output


class TestRegressions:
    def test_update_phase_row_without_position_errors_cleanly(self):
        """Regression: a missing position must yield a per-op error, not a
        KeyError traceback (run_ops only catches OpError/BackendError)."""
        mock = MagicMock(update_phase_row=MagicMock(), close=MagicMock())
        ops = [{"op": "update_phase_row", "id": 5}]
        result = _run(["--format", "json", "processes", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ops"][0]["status"] == "error"
        assert data["ops"][0]["error_code"] == "missing_field"
        mock.update_phase_row.assert_not_called()

    def test_ops_from_missing_file_is_usage_error_not_traceback(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["processes", "write", "--ops", "@/no/such/ops.json"], mock)
        assert result.exit_code != 0
        assert "Cannot read" in result.output
        assert "Traceback" not in result.output
