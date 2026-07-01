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


def _patch_auth():
    return [
        patch("expedait_cli.commands.projects.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.projects.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.projects.resolve_tenant_id", return_value=1),
    ]


def _run(args, mock):
    p = _patch_auth()
    with p[0], p[1], p[2], patch(
        "expedait_cli.commands.projects.ExpedaitClient", return_value=mock
    ):
        return CliRunner().invoke(cli, args)


class TestProjectsCreate:
    def test_create(self):
        mock = MagicMock(
            create_project=MagicMock(return_value={"id": 7, "name": "MVP"}), close=MagicMock(),
        )
        result = _run(
            ["--format", "json", "projects", "create", "--name", "MVP",
             "--process-id", "3", "--description", "the thing"],
            mock,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["affected_ids"] == [7]
        payload = mock.create_project.call_args.args[0]
        assert payload == {"name": "MVP", "project_type_id": 3, "description": "the thing"}

    def test_create_requires_process_id(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["projects", "create", "--name", "MVP"], mock)
        assert result.exit_code != 0
        assert "process-id" in result.output.lower() or "process_id" in result.output.lower()


class TestProjectsUpdate:
    def test_update(self):
        mock = MagicMock(
            update_project=MagicMock(return_value={"id": 7, "name": "MVP 2"}), close=MagicMock(),
        )
        result = _run(["projects", "update", "7", "--name", "MVP 2", "--repo-url", "https://g/x"], mock)
        assert result.exit_code == 0
        mock.update_project.assert_called_once_with(7, {"name": "MVP 2", "repo_url": "https://g/x"})

    def test_update_nothing_errors(self):
        mock = MagicMock(close=MagicMock())
        result = _run(["projects", "update", "7"], mock)
        assert result.exit_code != 0
        assert "Nothing to update" in result.output


class TestProjectsDelete:
    def test_preview_does_not_delete(self):
        mock = MagicMock(
            get_project=MagicMock(return_value={"id": 7, "name": "MVP"}),
            delete_project=MagicMock(),
            close=MagicMock(),
        )
        result = _run(["projects", "delete", "7"], mock)
        assert result.exit_code == 0
        assert "Nothing was deleted" in result.output
        assert "--confirm" in result.output
        mock.delete_project.assert_not_called()

    def test_confirm_deletes(self):
        mock = MagicMock(delete_project=MagicMock(return_value=None), close=MagicMock())
        result = _run(["--format", "json", "projects", "delete", "7", "--confirm"], mock)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_ok"] is True
        assert data["affected_ids"] == [7]
        mock.delete_project.assert_called_once_with(7)


class TestProjectsWriteOps:
    def test_multi_op_chain(self):
        mock = MagicMock(
            create_project=MagicMock(return_value={"id": 20, "name": "P"}),
            update_project=MagicMock(return_value={"id": 20, "name": "P2"}),
            close=MagicMock(),
        )
        ops = [
            {"op": "create_project", "ref": "p", "name": "P", "project_type_id": 3},
            {"op": "update_project", "id": "@p", "name": "P2"},
        ]
        result = _run(["--format", "json", "projects", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_ok"] is True
        mock.update_project.assert_called_once_with(20, {"name": "P2"})

    def test_delete_op_requires_confirm(self):
        mock = MagicMock(delete_project=MagicMock(), close=MagicMock())
        ops = [{"op": "delete_project", "id": 7}]
        result = _run(["--format", "json", "projects", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["all_ok"] is False
        assert data["ops"][0]["error_code"] == "confirm_required"
        mock.delete_project.assert_not_called()

    def test_delete_op_with_confirm(self):
        mock = MagicMock(delete_project=MagicMock(return_value=None), close=MagicMock())
        ops = [{"op": "delete_project", "id": 7, "confirm": True}]
        result = _run(["--format", "json", "projects", "write", "--ops", json.dumps(ops)], mock)
        assert result.exit_code == 0
        assert json.loads(result.output)["all_ok"] is True
        mock.delete_project.assert_called_once_with(7)


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
