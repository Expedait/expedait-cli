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

    def test_calls_download_with_project_id_only(self, tmp_path: Path):
        # The backend /download takes no format param; the client method is
        # download_project(project_id). Mock with the real signature (autospec)
        # so a future signature drift is caught here instead of at runtime —
        # the original tests mocked it loosely and let a `fmt=` crash ship.
        zip_bytes = _make_zip({"page.md": "# Hello"})
        from expedait_cli.client import ExpedaitClient
        mock_instance = MagicMock(spec=ExpedaitClient)
        mock_instance.download_project.return_value = zip_bytes
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             patch("expedait_cli.commands.projects.ExpedaitClient", return_value=mock_instance):

            runner = CliRunner()
            dest = str(tmp_path / "out")
            result = runner.invoke(cli, ["projects", "download", "1", "--output-dir", dest])

            assert result.exit_code == 0
            mock_instance.download_project.assert_called_once_with(1)

    def test_removed_download_format_option_is_rejected(self, tmp_path: Path):
        # --download-format never worked (backend has no format param); the dead
        # option was removed. Passing it should now be a usage error, not a crash.
        with patch("expedait_cli.commands.projects.resolve_token", return_value="tok"), \
             patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             _patch_client("download_project", _make_zip({"p.md": "x"})):
            result = CliRunner().invoke(
                cli, ["projects", "download", "1", "--download-format", "json"],
            )
            assert result.exit_code != 0
            assert "no such option" in result.output.lower()


class TestWorkspace:
    def test_workspace_json(self):
        from unittest.mock import patch as _p, MagicMock as _M
        from click.testing import CliRunner as _R
        from expedait_cli.main import cli as _cli
        data = {"phases": [{"name": "Discovery", "deliverables": []}]}
        mock = _M(get_workspace=_M(return_value=data), close=_M())
        with _p("expedait_cli.commands.projects.resolve_token", return_value="t"), \
             _p("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"), \
             _p("expedait_cli.commands.projects.resolve_tenant_id", return_value=1), \
             _p("expedait_cli.commands.projects.resolve_project_id", side_effect=lambda x: x), \
             _p("expedait_cli.commands.projects.ExpedaitClient", return_value=mock):
            result = _R().invoke(_cli, ["--format", "json", "projects", "workspace", "5"])
        assert result.exit_code == 0
        import json as _j
        assert _j.loads(result.output)["phases"][0]["name"] == "Discovery"
        mock.get_workspace.assert_called_once_with(5)
