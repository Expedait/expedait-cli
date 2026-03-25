"""Project-local settings stored in .expedait/settings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SETTINGS_DIR = ".expedait"
SETTINGS_FILE = "settings.json"


def _find_settings_path() -> Path:
    """Return .expedait/settings.json relative to cwd."""
    return Path.cwd() / SETTINGS_DIR / SETTINGS_FILE


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load project-local settings. Returns empty dict if missing."""
    p = path or _find_settings_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def save_settings(data: dict[str, Any], path: Path | None = None) -> None:
    """Write project-local settings, creating .expedait/ if needed."""
    p = path or _find_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")
