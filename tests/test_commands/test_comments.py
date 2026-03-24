"""Tests for comments commands."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_client(**methods):
    mock = MagicMock()
    for name, rv in methods.items():
        getattr(mock, name).return_value = rv
    return patch(
        "expedait_cli.commands.comments.ExpedaitClient",
        return_value=mock,
    )


def _patch_auth():
    """Patch all auth resolution for comments commands."""
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
        patches = _patch_auth()
        with patches[0], patches[1], patches[2], \
             _patch_client(list_comments=comments):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "comments", "list", "1"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 2
            assert data[0]["comment_text"] == "Fix this"


class TestCommentsCreate:
    def test_create_with_all_args(self):
        comment = {
            "id": 10,
            "comment_text": "Diverges from spec",
            "is_agent_comment": True,
            "source_page_id": 5,
        }
        patches = _patch_auth()
        with patches[0], patches[1], patches[2], \
             _patch_client(create_comment=comment) as mock_cls:

            runner = CliRunner()
            result = runner.invoke(cli, [
                "--format", "json",
                "comments", "create", "1",
                "--text", "Diverges from spec",
                "--selected-text", "some text",
                "--start-offset", "10",
                "--end-offset", "19",
                "--source-page-id", "5",
            ])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["is_agent_comment"] is True

            # Verify payload sent to client
            call_args = mock_cls.return_value.create_comment.call_args
            payload = call_args[0][1]
            assert payload["is_agent_comment"] is True
            assert payload["source_page_id"] == 5
            assert payload["comment_text"] == "Diverges from spec"

    def test_create_minimal(self):
        comment = {"id": 11, "comment_text": "Note", "is_agent_comment": True}
        patches = _patch_auth()
        with patches[0], patches[1], patches[2], \
             _patch_client(create_comment=comment):

            runner = CliRunner()
            result = runner.invoke(cli, [
                "--format", "json",
                "comments", "create", "1",
                "--text", "Note",
                "--selected-text", "x",
                "--start-offset", "0",
                "--end-offset", "1",
            ])

            assert result.exit_code == 0

    def test_create_missing_required(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "comments", "create", "1",
            "--text", "Note",
            # missing --selected-text, --start-offset, --end-offset
        ])

        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower() or "Error" in result.output


class TestCommentsResolve:
    def test_resolve(self):
        resolved = {"id": 1, "is_resolved": True}
        patches = _patch_auth()
        with patches[0], patches[1], patches[2], \
             _patch_client(resolve_comment=resolved):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "comments", "resolve", "1", "1"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["is_resolved"] is True


class TestCommentsDelete:
    def test_delete(self):
        patches = _patch_auth()
        with patches[0], patches[1], patches[2], \
             _patch_client(delete_comment={"ok": True}):

            runner = CliRunner()
            result = runner.invoke(cli, ["comments", "delete", "1", "1"])

            assert result.exit_code == 0
            assert "deleted" in result.output.lower()
