"""Tests for comments commands."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.comments.ExpedaitClient", return_value=mock)


def _patch_auth():
    return [
        patch("expedait_cli.commands.comments.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.comments.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.comments.resolve_tenant_id", return_value=1),
    ]


class TestCommentsList:
    def test_list_comments_json(self):
        comments = [
            {"id": 1, "comment_text": "Fix this", "is_resolved": False},
            {"id": 2, "comment_text": "Looks good", "is_resolved": True},
        ]
        mock = MagicMock(list_comments=MagicMock(return_value=comments), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "comments", "list", "1"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 2
            assert data[0]["comment_text"] == "Fix this"


class TestCommentsCreate:
    def test_create_with_explicit_offsets(self):
        comment = {"id": 10, "comment_text": "Diverges", "is_agent_comment": True, "source_deliverable_id": 5}
        mock = MagicMock(create_comment=MagicMock(return_value=comment), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, [
                "--format", "json", "comments", "create", "1",
                "--text", "Diverges",
                "--selected-text", "some text",
                "--start-offset", "10",
                "--end-offset", "19",
                "--source-deliverable-id", "5",
                "--agent-run-id", "42",
            ])
            assert result.exit_code == 0
            payload = mock.create_comment.call_args[0][1]
            assert payload["is_agent_comment"] is True
            assert payload["source_deliverable_id"] == 5
            assert payload["agent_run_id"] == 42
            assert payload["start_offset"] == 10
            assert payload["end_offset"] == 19
            # Offsets supplied explicitly -> no content fetch.
            mock.get_deliverable.assert_not_called()

    def test_create_resolves_offsets_from_content(self):
        deliverable = {"id": 1, "content": "Hello brave new world"}
        comment = {"id": 11, "comment_text": "Note", "is_agent_comment": True}
        mock = MagicMock(
            get_deliverable=MagicMock(return_value=deliverable),
            create_comment=MagicMock(return_value=comment),
            close=MagicMock(),
        )
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, [
                "--format", "json", "comments", "create", "1",
                "--text", "Note",
                "--selected-text", "brave",
            ])
            assert result.exit_code == 0
            payload = mock.create_comment.call_args[0][1]
            assert payload["start_offset"] == 6
            assert payload["end_offset"] == 11

    def test_create_offset_resolution_not_found(self):
        deliverable = {"id": 1, "content": "Hello world"}
        mock = MagicMock(get_deliverable=MagicMock(return_value=deliverable), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, [
                "comments", "create", "1",
                "--text", "Note",
                "--selected-text", "absent phrase",
            ])
            assert result.exit_code != 0
            assert "Could not find the selected text" in result.output

    def test_create_missing_required(self):
        result = CliRunner().invoke(cli, ["comments", "create", "1", "--text", "Note"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower()


class TestCommentsResolve:
    def test_resolve(self):
        mock = MagicMock(resolve_comment=MagicMock(return_value={"id": 2, "is_resolved": True}), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "comments", "resolve", "1", "2"])
            assert result.exit_code == 0
            assert json.loads(result.output)["is_resolved"] is True
            mock.resolve_comment.assert_called_once_with(1, 2)


class TestCommentsDelete:
    def test_delete(self):
        mock = MagicMock(delete_comment=MagicMock(return_value=None), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["comments", "delete", "1", "2"])
            assert result.exit_code == 0
            assert "deleted" in result.output.lower()
            mock.delete_comment.assert_called_once_with(1, 2)
