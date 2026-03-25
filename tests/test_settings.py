"""Tests for project-local settings."""

import json
from pathlib import Path

from expedait_cli.settings import load_settings, save_settings


class TestLoadSettings:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_settings(tmp_path / "nope.json") == {}

    def test_reads_valid_file(self, tmp_path: Path):
        p = tmp_path / ".expedait" / "settings.json"
        p.parent.mkdir()
        p.write_text(json.dumps({"tenant_id": 3, "project_id": 7}))
        assert load_settings(p) == {"tenant_id": 3, "project_id": 7}


class TestSaveSettings:
    def test_creates_file_and_dir(self, tmp_path: Path):
        p = tmp_path / ".expedait" / "settings.json"
        save_settings({"tenant_id": 1, "project_id": 2}, p)
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["tenant_id"] == 1
        assert data["project_id"] == 2

    def test_overwrites_existing(self, tmp_path: Path):
        p = tmp_path / ".expedait" / "settings.json"
        save_settings({"project_id": 1}, p)
        save_settings({"project_id": 2}, p)
        assert json.loads(p.read_text())["project_id"] == 2
