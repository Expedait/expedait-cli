"""Output formatting: JSON vs human-readable text."""

from __future__ import annotations

import json
import sys
from typing import Any


def is_tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def output(data: Any, fmt: str | None = None) -> None:
    """Print data in the requested format."""
    effective = fmt or ("text" if is_tty() else "json")
    if effective == "json":
        click_echo_json(data)
    else:
        click_echo_text(data)


def click_echo_json(data: Any) -> None:
    import click
    click.echo(json.dumps(data, indent=2, default=str))


def click_echo_text(data: Any) -> None:
    import click
    if isinstance(data, list):
        _print_table(data)
    elif isinstance(data, dict):
        _print_dict(data)
    else:
        click.echo(str(data))


def _print_table(rows: list[dict[str, Any]]) -> None:
    import click
    if not rows:
        click.echo("No results.")
        return
    keys = list(rows[0].keys())
    # Compute column widths
    widths = {k: len(k) for k in keys}
    for row in rows:
        for k in keys:
            widths[k] = max(widths[k], len(str(row.get(k, ""))))
    # Header
    header = "  ".join(k.ljust(widths[k]) for k in keys)
    click.echo(header)
    click.echo("  ".join("-" * widths[k] for k in keys))
    # Rows
    for row in rows:
        line = "  ".join(str(row.get(k, "")).ljust(widths[k]) for k in keys)
        click.echo(line)


def _print_dict(d: dict[str, Any]) -> None:
    import click
    if not d:
        click.echo("Empty.")
        return
    max_key = max(len(str(k)) for k in d)
    for k, v in d.items():
        click.echo(f"{str(k).ljust(max_key)}  {v}")
