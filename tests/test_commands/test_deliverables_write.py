"""Tests for the deliverables write surface (mirrors MCP write_deliverable)."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.client import BackendError
from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.deliverables.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.deliverables.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.deliverables.resolve_tenant_id", return_value=1),
        patch("expedait_cli.commands.deliverables.resolve_project_id", side_effect=lambda x: x),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.deliverables.ExpedaitClient", return_value=mock)


def _run(args, mock):
    p = _patch_auth()
    with p[0], p[1], p[2], p[3], _patch_client(mock):
        return CliRunner().invoke(cli, args)


class TestCreate:
    def test_create_json(self):
        mock = MagicMock(
            create_deliverable=MagicMock(return_value={"id": 5}), close=MagicMock(),
        )
        result = _run(
            ["--format", "json", "deliverables", "create",
             "--project", "1", "--type", "3", "--title", "Vision"],
            mock,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_ok"] is True
        assert data["affected_deliverable_ids"] == [5]
        payload = mock.create_deliverable.call_args.args[0]
        assert payload == {"title": "Vision", "project_id": 1, "deliverable_type_id": 3}

    def test_create_with_inline_content_and_parent(self):
        mock = MagicMock(
            create_deliverable=MagicMock(return_value={"id": 8}), close=MagicMock(),
        )
        result = _run(
            ["--format", "json", "deliverables", "create",
             "--project", "1", "--type", "3", "--title", "Child",
             "--content", "# Body", "--parent-deliverable-id", "2"],
            mock,
        )
        assert result.exit_code == 0
        payload = mock.create_deliverable.call_args.args[0]
        assert payload["content"] == "# Body"
        assert payload["parent_deliverable_id"] == 2

    def test_create_requires_project(self):
        mock = MagicMock(close=MagicMock())
        p = _patch_auth()
        # resolve_project_id returns None -> usage error.
        with p[0], p[1], p[2], \
                patch("expedait_cli.commands.deliverables.resolve_project_id", return_value=None), \
                _patch_client(mock):
            result = CliRunner().invoke(
                cli, ["deliverables", "create", "--type", "3", "--title", "X"],
            )
        assert result.exit_code != 0
        assert "No project ID" in result.output


class TestEditRenameStateVersion:
    def test_edit_content(self):
        mock = MagicMock(
            update_deliverable=MagicMock(return_value={"id": 4}), close=MagicMock(),
        )
        result = _run(["deliverables", "edit", "4", "--content", "new body"], mock)
        assert result.exit_code == 0
        mock.update_deliverable.assert_called_once_with(4, {"content": "new body"})

    def test_rename(self):
        mock = MagicMock(
            update_deliverable=MagicMock(return_value={"id": 4, "title": "Renamed"}),
            close=MagicMock(),
        )
        result = _run(["deliverables", "rename", "4", "--title", "Renamed"], mock)
        assert result.exit_code == 0
        mock.update_deliverable.assert_called_once_with(4, {"title": "Renamed"})

    def test_set_state(self):
        mock = MagicMock(
            set_deliverable_state=MagicMock(return_value={"id": 4, "state": "Review"}),
            close=MagicMock(),
        )
        result = _run(["deliverables", "set-state", "4", "--state", "Review"], mock)
        assert result.exit_code == 0
        mock.set_deliverable_state.assert_called_once_with(4, "Review", None)

    def test_set_state_invalid_choice(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["deliverables", "set-state", "4", "--state", "Bogus"], mock)
        assert result.exit_code != 0

    def test_save_version(self):
        mock = MagicMock(
            save_deliverable_version=MagicMock(
                return_value={"id": 9, "version_number": 3}),
            close=MagicMock(),
        )
        result = _run(["deliverables", "save-version", "4", "--reason", "snap"], mock)
        assert result.exit_code == 0
        mock.save_deliverable_version.assert_called_once_with(4, "snap")


class TestWriteOps:
    def test_chain_with_last(self):
        mock = MagicMock(
            create_deliverable=MagicMock(return_value={"id": 7}),
            set_deliverable_state=MagicMock(return_value={"id": 7, "state": "Review"}),
            close=MagicMock(),
        )
        ops = [
            {"op": "create", "project_id": 1, "deliverable_type_id": 3, "title": "T"},
            {"op": "set_state", "id": "$last", "state": "Review"},
        ]
        result = _run(["--format", "json", "deliverables", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_ok"] is True
        assert data["affected_deliverable_ids"] == [7]
        mock.set_deliverable_state.assert_called_once_with(7, "Review", None)

    def test_named_ref(self):
        mock = MagicMock(
            create_deliverable=MagicMock(return_value={"id": 11}),
            update_deliverable=MagicMock(return_value={"id": 11, "title": "R"}),
            close=MagicMock(),
        )
        ops = [
            {"op": "create", "ref": "x", "project_id": 1, "deliverable_type_id": 3, "title": "T"},
            {"op": "rename", "id": "@x", "title": "R"},
        ]
        result = _run(["--format", "json", "deliverables", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        mock.update_deliverable.assert_called_once_with(11, {"title": "R"})

    def test_partial_failure_skips_rest(self):
        mock = MagicMock(
            set_deliverable_state=MagicMock(side_effect=BackendError(423, "locked")),
            update_deliverable=MagicMock(),
            close=MagicMock(),
        )
        ops = [
            {"op": "set_state", "id": 1, "state": "Review"},
            {"op": "rename", "id": 1, "title": "Y"},
        ]
        result = _run(["--format", "json", "deliverables", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["all_ok"] is False
        assert data["ops"][0]["status"] == "error"
        assert data["ops"][0]["error_status"] == 423
        assert data["ops"][1]["status"] == "skipped"
        mock.update_deliverable.assert_not_called()

    def test_preflight_rejects_bad_op(self):
        mock = MagicMock(close=MagicMock())
        ops = [{"op": "frobnicate", "id": 1}]
        result = _run(["deliverables", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        assert "invalid" in result.output.lower()
        mock.create_deliverable.assert_not_called()

    def test_preflight_rejects_dangling_last(self):
        mock = MagicMock(close=MagicMock())
        ops = [{"op": "edit", "id": "$last", "content": "x"}]
        result = _run(["deliverables", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        assert "$last" in result.output


class TestTypesCommand:
    def test_list_types_json(self):
        items = [{"id": 3, "name": "Vision", "abbreviation": "VIS",
                  "is_objective": False, "phase_id": 10}]
        mock = MagicMock(list_deliverable_types=MagicMock(return_value=items), close=MagicMock())
        result = _run(["--format", "json", "deliverables", "types"], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["name"] == "Vision"


class TestReadArgErrors:
    def test_content_from_missing_file_is_usage_error(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["deliverables", "edit", "1", "--content", "@/no/such/file.md"], mock)
        assert result.exit_code != 0
        assert "Cannot read" in result.output
        assert "Traceback" not in result.output
