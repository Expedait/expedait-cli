"""Tests for pages commands."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _patch_client(method: str, return_value):
    return patch(
        "expedait_cli.commands.pages.ExpedaitClient",
        return_value=MagicMock(**{method: MagicMock(return_value=return_value), "close": MagicMock()}),
    )


class TestPagesList:
    def test_json_output(self):
        pages = [{"id": 1, "title": "Vision", "state": "In Progress", "version": 2}]
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             _patch_client("list_pages", pages):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "pages", "list", "--project-id", "1"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data[0]["title"] == "Vision"


class TestPagesGet:
    def test_prints_markdown(self):
        page = {"id": 1, "title": "Vision", "content": "# Product Vision\n\nOur product..."}
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             _patch_client("get_page", page):

            runner = CliRunner()
            result = runner.invoke(cli, ["pages", "get", "1"])

            assert result.exit_code == 0
            assert "# Product Vision" in result.output

    def test_json_output(self):
        page = {"id": 1, "title": "Vision", "content": "# Vision"}
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             _patch_client("get_page", page):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "pages", "get", "1"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["title"] == "Vision"

    def test_empty_page(self):
        page = {"id": 1, "title": "Empty", "content": None}
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             _patch_client("get_page", page):

            runner = CliRunner()
            result = runner.invoke(cli, ["pages", "get", "1"])

            assert result.exit_code == 0
            assert "(empty page)" in result.output


class TestPagesFull:
    def test_full_context(self):
        full = {
            "page": {"id": 1, "title": "Vision"},
            "is_locked": False,
            "comments": [],
            "dependencies": [],
        }
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             _patch_client("get_page_full", full):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "pages", "full", "1"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["is_locked"] is False


class TestPagesDownload:
    def test_download_and_extract(self, tmp_path: Path):
        zip_bytes = _make_zip({"vision.md": "# Vision"})
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             _patch_client("download_page", zip_bytes):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["pages", "download", "1", "--output-dir", dest])

            assert result.exit_code == 0
            assert (Path(dest) / "vision.md").read_text() == "# Vision"

    def test_default_format_is_markdown(self, tmp_path: Path):
        zip_bytes = _make_zip({"vision.md": "# Vision"})
        mock_download = MagicMock(return_value=zip_bytes)
        mock_instance = MagicMock(download_page=mock_download, close=MagicMock())
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             patch("expedait_cli.commands.pages.ExpedaitClient", return_value=mock_instance):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["pages", "download", "1", "--output-dir", dest])

            assert result.exit_code == 0
            mock_download.assert_called_once_with(1, fmt="markdown")

    def test_json_format(self, tmp_path: Path):
        zip_bytes = _make_zip({"vision.json": '{"title": "Vision"}'})
        mock_download = MagicMock(return_value=zip_bytes)
        mock_instance = MagicMock(download_page=mock_download, close=MagicMock())
        with patch("expedait_cli.commands.pages.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.pages.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.pages.resolve_tenant_id", return_value=1), \
             patch("expedait_cli.commands.pages.ExpedaitClient", return_value=mock_instance):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["pages", "download", "1", "--output-dir", dest, "--download-format", "json"])

            assert result.exit_code == 0
            mock_download.assert_called_once_with(1, fmt="json")
