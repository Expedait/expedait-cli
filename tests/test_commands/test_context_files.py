"""Tests for context-file management (attachments feeding LLM context)."""

import json
from pathlib import Path
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


def _run(args, mock):
    p = _patch_auth()
    with p[0], p[1], p[2], _patch_client(mock):
        return CliRunner().invoke(cli, args)


class TestListFiles:
    def test_json(self):
        items = [{"id": 7, "filename": "spec.md", "file_type": "text/markdown",
                  "file_size": 1234, "excluded_from_context": False}]
        mock = MagicMock(list_deliverable_files=MagicMock(return_value=items), close=MagicMock())
        result = _run(["--format", "json", "context", "files", "1"], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["filename"] == "spec.md"


class TestAddFile:
    def test_upload(self, tmp_path: Path):
        f = tmp_path / "ref.md"
        f.write_text("# Reference")
        mock = MagicMock(
            upload_deliverable_file=MagicMock(return_value={"id": 9, "filename": "ref.md"}),
            close=MagicMock(),
        )
        result = _run(["--format", "json", "context", "add", "1", str(f)], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)["id"] == 9
        call = mock.upload_deliverable_file.call_args
        assert call.args[0] == 1
        assert call.args[1] == "ref.md"
        assert call.args[2] == b"# Reference"
        # markdown content type guessed from extension
        assert call.args[3] in ("text/markdown", "text/x-markdown")

    def test_upload_with_name_override(self, tmp_path: Path):
        f = tmp_path / "local.txt"
        f.write_text("data")
        mock = MagicMock(
            upload_deliverable_file=MagicMock(return_value={"id": 10, "filename": "renamed.txt"}),
            close=MagicMock(),
        )
        result = _run(["context", "add", "1", str(f), "--name", "renamed.txt"], mock)
        assert result.exit_code == 0
        assert mock.upload_deliverable_file.call_args.args[1] == "renamed.txt"

    def test_missing_file_errors(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["context", "add", "1", "/no/such/file.md"], mock)
        assert result.exit_code != 0


class TestFileContent:
    def test_text_output(self):
        mock = MagicMock(
            get_deliverable_file_content=MagicMock(
                return_value={"content": "parsed text", "char_count": 11}),
            close=MagicMock(),
        )
        result = _run(["context", "file-content", "9"], mock)
        assert result.exit_code == 0
        assert "parsed text" in result.output

    def test_empty(self):
        mock = MagicMock(
            get_deliverable_file_content=MagicMock(return_value={"content": ""}),
            close=MagicMock(),
        )
        result = _run(["context", "file-content", "9"], mock)
        assert result.exit_code == 0
        assert "not yet parsed" in result.output


class TestDownloadFile:
    def test_writes_bytes(self, tmp_path: Path):
        mock = MagicMock(
            download_deliverable_file=MagicMock(return_value=b"raw-bytes"),
            close=MagicMock(),
        )
        dest = tmp_path / "out.bin"
        result = _run(["context", "download-file", "9", "-o", str(dest)], mock)
        assert result.exit_code == 0
        assert dest.read_bytes() == b"raw-bytes"


class TestRemoveFile:
    def test_delete(self):
        mock = MagicMock(delete_deliverable_file=MagicMock(return_value=None), close=MagicMock())
        result = _run(["context", "remove-file", "9"], mock)
        assert result.exit_code == 0
        mock.delete_deliverable_file.assert_called_once_with(9)


class TestSetFile:
    def test_exclude(self):
        mock = MagicMock(
            set_deliverable_file_excluded=MagicMock(
                return_value={"id": 9, "excluded_from_context": True}),
            close=MagicMock(),
        )
        result = _run(["context", "set-file", "9", "--exclude"], mock)
        assert result.exit_code == 0
        mock.set_deliverable_file_excluded.assert_called_once_with(9, True)

    def test_include(self):
        mock = MagicMock(
            set_deliverable_file_excluded=MagicMock(
                return_value={"id": 9, "excluded_from_context": False}),
            close=MagicMock(),
        )
        result = _run(["context", "set-file", "9", "--include"], mock)
        assert result.exit_code == 0
        mock.set_deliverable_file_excluded.assert_called_once_with(9, False)

    def test_requires_flag(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["context", "set-file", "9"], mock)
        assert result.exit_code != 0
