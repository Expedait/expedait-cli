"""Tests for review commands."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _patch_auth():
    return [
        patch("expedait_cli.commands.review.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.review.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.review.resolve_tenant_id", return_value=1),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.review.ExpedaitClient", return_value=mock)


class TestReviewIssues:
    def test_list_json_default_state_all(self):
        issues = [{
            "id": 7, "severity": "high", "state": "open", "description": "Missing AC",
            "criteria": [{"key": "completeness", "display_name": "Completeness"}],
            "anchor": {"start_offset": 5, "end_offset": 12, "selected_text": "foo"},
        }]
        mock = MagicMock(list_review_issues=MagicMock(return_value=issues), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "review", "issues", "1"])
            assert result.exit_code == 0
            assert json.loads(result.output)[0]["id"] == 7
            mock.list_review_issues.assert_called_once_with(1, state="all")

    def test_state_filter_passed(self):
        mock = MagicMock(list_review_issues=MagicMock(return_value=[]), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["review", "issues", "1", "--state", "open"])
            assert result.exit_code == 0
            mock.list_review_issues.assert_called_once_with(1, state="open")


class TestReviewMute:
    def test_mute(self):
        mock = MagicMock(mute_review_issue=MagicMock(return_value={"id": 7, "state": "muted"}), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "review", "mute", "7", "--note", "by design"])
            assert result.exit_code == 0
            mock.mute_review_issue.assert_called_once_with(7, muted=True, note="by design")

    def test_unmute(self):
        mock = MagicMock(mute_review_issue=MagicMock(return_value={"id": 7, "state": "open"}), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "review", "mute", "7", "--unmute"])
            assert result.exit_code == 0
            mock.mute_review_issue.assert_called_once_with(7, muted=False, note=None)
