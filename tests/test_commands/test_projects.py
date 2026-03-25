"""Tests for projects commands."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from expedait_cli.main import cli


def _make_zip(files: dict[str, str]) -> bytes:
    """Create a ZIP bytes with given filename→content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _patch_client(method: str, return_value):
    """Patch a method on ExpedaitClient instances."""
    return patch(
        "expedait_cli.commands.projects.ExpedaitClient",
        return_value=MagicMock(**{method: MagicMock(return_value=return_value), "close": MagicMock()}),
    )


class TestProjectsList:
    def test_json_output(self):
        projects = [{"id": 1, "name": "P1"}, {"id": 2, "name": "P2"}]
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             _patch_client("list_projects", projects):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "projects", "list"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 2
            assert data[0]["name"] == "P1"

    def test_text_output(self):
        projects = [{"id": 1, "name": "P1", "project_type_name": "SaaS", "state": "active"}]
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             _patch_client("list_projects", projects):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "text", "projects", "list"])

            assert result.exit_code == 0
            assert "P1" in result.output


class TestProjectsGet:
    def test_get_project(self):
        project = {"id": 1, "name": "My Project", "description": "desc"}
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             _patch_client("get_project", project):

            runner = CliRunner()
            result = runner.invoke(cli, ["--format", "json", "projects", "get", "1"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["name"] == "My Project"


class TestProjectsDownload:
    def test_download_and_extract(self, tmp_path: Path):
        zip_bytes = _make_zip({"page1.md": "# Hello", "page2.md": "# World"})
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             _patch_client("download_project", zip_bytes):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["projects", "download", "1", "--output-dir", dest])

            assert result.exit_code == 0
            assert (Path(dest) / "page1.md").read_text() == "# Hello"
            assert (Path(dest) / "page2.md").read_text() == "# World"

    def test_default_format_is_markdown(self, tmp_path: Path):
        zip_bytes = _make_zip({"page.md": "# Hello"})
        mock_download = MagicMock(return_value=zip_bytes)
        mock_instance = MagicMock(download_project=mock_download, close=MagicMock())
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             patch("expedait_cli.commands.projects.ExpedaitClient", return_value=mock_instance):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["projects", "download", "1", "--output-dir", dest])

            assert result.exit_code == 0
            mock_download.assert_called_once_with(1, fmt="markdown")

    def test_json_format(self, tmp_path: Path):
        zip_bytes = _make_zip({"page.json": '{"title": "Hello"}'})
        mock_download = MagicMock(return_value=zip_bytes)
        mock_instance = MagicMock(download_project=mock_download, close=MagicMock())
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             patch("expedait_cli.commands.projects.ExpedaitClient", return_value=mock_instance):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["projects", "download", "1", "--output-dir", dest, "--download-format", "json"])

            assert result.exit_code == 0
            mock_download.assert_called_once_with(1, fmt="json")
