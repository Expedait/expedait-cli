"""Configuration file management for ~/.expedait/config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIG_DIR = Path.home() / ".expedait"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from disk. Returns empty dict if missing."""
    p = path or CONFIG_FILE
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    """Write config to disk, creating directory if needed."""
    p = path or CONFIG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def clear_config(path: Path | None = None) -> None:
    """Remove config file."""
    p = path or CONFIG_FILE
    if p.exists():
        p.unlink()
