"""Tests for deliverables commands (and the deprecated pages alias)."""

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


def _patch_auth():
    return [
        patch("expedait_cli.commands.deliverables.resolve_token", return_value="tok"),
        patch("expedait_cli.commands.deliverables.resolve_api_url", return_value="http://x"),
        patch("expedait_cli.commands.deliverables.resolve_tenant_id", return_value=1),
        patch("expedait_cli.commands.deliverables.resolve_project_id", side_effect=lambda x: x),
    ]


def _patch_client(mock: MagicMock):
    return patch("expedait_cli.commands.deliverables.ExpedaitClient", return_value=mock)


class TestDeliverablesList:
    def test_json_output(self):
        items = [{"id": 1, "title": "Vision", "state": "In Progress", "version": 2, "parent_deliverable_id": None}]
        mock = MagicMock(list_deliverables=MagicMock(return_value=items), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "deliverables", "list", "--project-id", "1"])
            assert result.exit_code == 0
            assert json.loads(result.output)[0]["title"] == "Vision"


class TestDeliverablesGet:
    def test_default_prints_content(self):
        deliverable = {"id": 1, "title": "Vision", "content": "# Product Vision", "deliverable_type_id": 3}
        mock = MagicMock(get_deliverable=MagicMock(return_value=deliverable), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(cli, ["deliverables", "get", "1"])
            assert result.exit_code == 0
            assert "# Product Vision" in result.output

    def test_empty_content(self):
        deliverable = {"id": 1, "title": "Empty", "content": None, "deliverable_type_id": 3}
        mock = MagicMock(get_deliverable=MagicMock(return_value=deliverable), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(cli, ["deliverables", "get", "1"])
            assert result.exit_code == 0
            assert "(empty deliverable)" in result.output

    def test_include_meta_surfaces_parent(self):
        deliverable = {
            "id": 2, "title": "Child", "content": "x", "state": "Approved",
            "deliverable_type_id": 3, "parent_deliverable_id": 1,
        }
        mock = MagicMock(get_deliverable=MagicMock(return_value=deliverable), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "deliverables", "get", "2", "--include", "meta"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["meta"]["parent_deliverable_id"] == 1

    def test_include_dependencies_and_score(self):
        deliverable = {"id": 1, "deliverable_type_id": 3}
        full = {
            "dependencies": [{"deliverable_id": 9, "content": "dep"}],
            "is_locked": False,
            "unmet_dependencies": [],
            "versions": [{"version_number": 2, "score": 88, "score_breakdown": {}, "scoring_status": "complete"}],
        }
        mock = MagicMock(
            get_deliverable=MagicMock(return_value=deliverable),
            get_deliverable_full=MagicMock(return_value=full),
            close=MagicMock(),
        )
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(
                cli, ["--format", "json", "deliverables", "get", "1", "--include", "dependencies,score"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["dependencies"][0]["deliverable_id"] == 9
            assert data["score"]["score"] == 88

    def test_unknown_include_section_errors(self):
        p = _patch_auth()
        with p[0], p[1], p[2], p[3]:
            result = CliRunner().invoke(cli, ["deliverables", "get", "1", "--include", "bogus"])
            assert result.exit_code != 0
            assert "Unknown include section" in result.output


class TestDeliverablesInspect:
    def test_inspect(self):
        full = {"id": 1, "is_locked": False, "comments": [], "dependencies": []}
        mock = MagicMock(get_deliverable_full=MagicMock(return_value=full), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(cli, ["--format", "json", "deliverables", "inspect", "1"])
            assert result.exit_code == 0
            assert json.loads(result.output)["is_locked"] is False


class TestDeliverablesDownload:
    def test_download_and_extract(self, tmp_path: Path):
        zip_bytes = _make_zip({"vision.md": "# Vision"})
        mock = MagicMock(download_deliverable=MagicMock(return_value=zip_bytes), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            dest = str(tmp_path / "out")
            result = CliRunner().invoke(cli, ["deliverables", "download", "1", "--output-dir", dest])
            assert result.exit_code == 0
            assert (Path(dest) / "vision.md").read_text() == "# Vision"


class TestPagesAlias:
    def test_pages_still_works_and_warns(self):
        deliverable = {"id": 1, "title": "Vision", "content": "# Vision", "deliverable_type_id": 3}
        mock = MagicMock(get_deliverable=MagicMock(return_value=deliverable), close=MagicMock())
        p = _patch_auth()
        with p[0], p[1], p[2], p[3], _patch_client(mock):
            result = CliRunner().invoke(cli, ["pages", "get", "1"])
            assert result.exit_code == 0
            assert "# Vision" in result.output
            assert "deprecated" in result.output.lower()
