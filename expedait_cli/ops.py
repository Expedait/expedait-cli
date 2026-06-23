"""Shared multi-op write engine — the CLI mirror of the MCP server's
``write_*`` tools (``backend/app/mcp_server/tools/_common.py``).

``deliverables write``, ``processes write``, and ``roles write`` all accept an
ordered list of ops, execute them sequentially, stop on the first failure
(subsequent ops are ``skipped``), and return a per-op result array so the
caller knows exactly which ops landed.

References between ops:
  - ``@name`` — a named ref bound by an earlier create op (the op carries
    ``ref: "name"``). The single mechanism that works when ops chain across
    multiple entity kinds (a process build touches process, phase, row, and
    deliverable-type ids — one positional ``$last`` slot cannot disambiguate
    them).
  - ``$last`` — the id touched by the immediately-preceding op. Kept for the
    deliverable surface where every op touches the same entity kind.
  - an int — a literal id.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import click

from .client import BackendError
from .formatters import is_tty, output


def read_value_arg(value: str | None) -> str | None:
    """Resolve a CLI value that may be inline, ``@file``, or ``-`` (stdin).

    Shared by ``--content`` / ``--instructions`` / ``--ops`` across command
    groups. A missing/unreadable ``@file`` raises a clean ``click.UsageError``
    instead of letting an ``OSError`` traceback escape to the user."""
    if value is None:
        return None
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:])
        try:
            return path.read_text()
        except OSError as exc:
            raise click.UsageError(f"Cannot read {path}: {exc}")
    return value


class OpError(Exception):
    """A per-op runtime failure carrying an actionable, structured payload: a
    machine code, a human-readable message, and a concrete fix hint — so a
    calling agent can self-correct without a human."""

    def __init__(self, code: str, message: str, *, fix_hint: str | None = None, **extra: Any):
        super().__init__(message)
        self.payload: dict = {"error_code": code, "error": message}
        if fix_hint:
            self.payload["fix_hint"] = fix_hint
        self.payload.update(extra)


class RefResolver:
    """Resolves op id references to concrete ids. ``bind()`` records a named ref
    from a create op; ``note()`` records the last-touched id for ``$last``."""

    def __init__(self) -> None:
        self._named: dict = {}
        self._last: int | None = None

    def bind(self, name: str | None, value: int | None) -> None:
        if name and value is not None:
            self._named[name] = value

    def note(self, value: int | None) -> None:
        if value is not None:
            self._last = value

    def resolve(self, raw: Any, *, kind: str = "id") -> int:
        if isinstance(raw, str):
            if raw == "$last":
                if self._last is None:
                    raise OpError(
                        "bad_ref", "$last has no preceding id",
                        fix_hint=(
                            "create or reference an entity in an earlier op, "
                            f"or pass a numeric {kind}"
                        ),
                    )
                return self._last
            if raw.startswith("@"):
                name = raw[1:]
                if name not in self._named:
                    raise OpError(
                        "bad_ref", f"unknown ref {raw!r}",
                        fix_hint=(
                            f"bind it earlier with a create op that sets "
                            f"ref:{name!r}, or pass a numeric {kind}"
                        ),
                    )
                return self._named[name]
        # bool is an int subclass — exclude it explicitly.
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        raise OpError(
            "bad_ref",
            f"{kind} must be an int, '$last', or '@name'; got {raw!r}",
            fix_hint=f"pass a numeric {kind} or a @ref bound by an earlier create op",
        )


# A handler runs one op. It returns ``(result_fields, touched_id)``:
#   result_fields — merged into the op's result entry (e.g. ``{"id": 7}``)
#   touched_id    — id to record for ``$last`` and surface as affected
#                   (``None`` when the op touches nothing, e.g. a pure set).
OpHandler = Callable[[dict, RefResolver], "tuple[dict, int | None]"]


def run_ops(ops: list[dict], handlers: dict[str, OpHandler]) -> tuple[list[dict], set]:
    """Execute ops sequentially with stop-on-first-failure semantics.

    Returns ``(results, affected_ids)``. ``results`` is one entry per op with a
    ``status`` of ``ok`` | ``error`` | ``skipped``. A handler raising
    :class:`OpError` yields a structured error entry; a :class:`BackendError`
    yields ``{error_status, error}``. The caller owns pre-flight shape
    validation."""
    results: list[dict] = []
    refs = RefResolver()
    affected: set = set()
    failed = False

    for i, op in enumerate(ops):
        op_type = op.get("op")
        if failed:
            results.append({"index": i, "op": op_type, "status": "skipped"})
            continue
        handler = handlers.get(op_type)
        if handler is None:
            results.append({
                "index": i, "op": op_type, "status": "error",
                "error_code": "unknown_op", "error": f"unknown op {op_type!r}",
            })
            failed = True
            continue
        try:
            result_fields, touched = handler(op, refs)
            entry = {"index": i, "op": op_type, "status": "ok"}
            entry.update(result_fields or {})
            results.append(entry)
            refs.note(touched)
            if touched is not None:
                affected.add(touched)
        except OpError as exc:
            results.append({"index": i, "op": op_type, "status": "error", **exc.payload})
            failed = True
        except BackendError as exc:
            results.append({
                "index": i, "op": op_type, "status": "error",
                "error_status": exc.status, "error": str(exc.body),
            })
            failed = True

    return results, affected


def render_ops(
    ctx: click.Context,
    results: list[dict],
    affected: set,
    *,
    affected_key: str = "affected_ids",
) -> None:
    """Print the run_ops result per ``--format``, then exit non-zero if any op
    failed — so scripts can detect partial application. JSON mirrors the MCP
    tool response (``ops`` / ``all_ok`` / affected ids)."""
    all_ok = all(r.get("status") == "ok" for r in results)
    payload = {"ops": results, "all_ok": all_ok, affected_key: sorted(affected)}

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(payload, "json")
    else:
        for r in results:
            status = r.get("status")
            line = f"[{r.get('index')}] {r.get('op')}: {status}"
            if status == "ok":
                extra = {
                    k: v for k, v in r.items()
                    if k not in ("index", "op", "status")
                }
                if extra:
                    line += "  " + ", ".join(f"{k}={v}" for k, v in extra.items())
            elif status == "error":
                line += f"  {r.get('error_code', r.get('error_status', ''))}: {r.get('error', '')}"
                if r.get("fix_hint"):
                    line += f" (hint: {r['fix_hint']})"
            click.echo(line)
        summary = "all ops ok" if all_ok else "completed with errors"
        click.echo(f"{summary}; affected: {sorted(affected) or '(none)'}")

    if not all_ok:
        ctx.exit(1)
