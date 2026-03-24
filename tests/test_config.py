"""Tests for config file read/write."""

import json
from pathlib import Path

from expedait_cli.config import load_config, save_config, clear_config


class TestLoadConfig:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_config(tmp_path / "nope.json") == {}

    def test_reads_valid_file(self, saved_config: Path):
        cfg = load_config(saved_config)
        assert cfg["token"] == "test-token-abc"
        assert cfg["tenant_id"] == 1


class TestSaveConfig:
    def test_creates_file(self, config_path: Path):
        save_config({"token": "abc"}, config_path)
        assert config_path.exists()
        assert json.loads(config_path.read_text())["token"] == "abc"

    def test_creates_parent_dirs(self, tmp_path: Path):
        p = tmp_path / "a" / "b" / "config.json"
        save_config({"x": 1}, p)
        assert p.exists()

    def test_overwrites_existing(self, saved_config: Path):
        save_config({"token": "new"}, saved_config)
        assert json.loads(saved_config.read_text())["token"] == "new"


class TestClearConfig:
    def test_removes_file(self, saved_config: Path):
        clear_config(saved_config)
        assert not saved_config.exists()

    def test_noop_if_missing(self, tmp_path: Path):
        clear_config(tmp_path / "nope.json")  # no error
