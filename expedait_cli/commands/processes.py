"""Process (Process Designer) commands: list, get, write.

A *process* is a project type plus the template tree it owns: phases → rows →
deliverable-type cards, dependency edges between cards, owner roles, and
objective subprocesses (a card flagged ``is_objective`` owns its own inner set
of phases). It is the TEMPLATE layer — editing it reshapes every project
instantiated from the process.

This mirrors the MCP ``list_processes`` / ``get_process`` / ``write_process``
tools (``backend/app/mcp_server/tools/process.py``), hitting the same REST
endpoints directly.
"""

from __future__ import annotations

import json

import click

from ..auth import resolve_api_url, resolve_tenant_id, resolve_token
from ..client import ExpedaitClient
from ..formatters import is_tty, output
from ..ops import OpError, RefResolver, read_value_arg, render_ops, run_ops


# Cards and rows are positioned with floats so inserts never renumber. We never
# ask the user for a coordinate; when one is omitted we append a fresh card a
# full step past the current max, or (with after_type_id) drop it on the
# midpoint just past an anchor card. Mirrors the MCP write_process layout logic.
COL_STEP = 1000.0
ROW_STEP = 1000.0

PROCESS_OPS_MAX = 50
MAX_SUBPROCESS_DEPTH = 25
TYPES_PAGE_SIZE = 200
TYPES_MAX_PAGES = 25
PROJECTS_PAGE_SIZE = 200
PROJECTS_MAX_PAGES = 100

VALID_PROCESS_OPS = {
    "create_process", "update_process", "duplicate_process", "delete_process",
    "create_phase", "update_phase", "delete_phase",
    "create_phase_row", "update_phase_row", "delete_phase_row",
    "create_deliverable_type", "update_deliverable_type", "delete_deliverable_type",
    "set_dependencies", "set_owner_roles",
}
_CREATE_OPS = {
    "create_process", "duplicate_process", "create_phase",
    "create_phase_row", "create_deliverable_type",
}


def _make_client(ctx: click.Context) -> ExpedaitClient:
    token = resolve_token()
    api_url = resolve_api_url(ctx.obj.get("api_url"))
    tenant_id = resolve_tenant_id(ctx.obj.get("tenant_id"))
    return ExpedaitClient(api_url, token, tenant_id)




# --------------------------------------------------------------------------
# Pre-flight shape validation (whole-call reject before any backend write).
# --------------------------------------------------------------------------


def _require(op: dict, i: int, *fields: str) -> None:
    for f in fields:
        if op.get(f) in (None, ""):
            raise click.UsageError(f"ops[{i}] ({op.get('op')}): {f} is required.")


def _check_ref(op: dict, i: int) -> None:
    ref = op.get("ref")
    if ref is not None and (not isinstance(ref, str) or not ref.strip()):
        raise click.UsageError(f"ops[{i}] ({op.get('op')}): ref must be a non-empty string.")


def _preflight_validate(ops: list[dict]) -> None:
    if not ops:
        raise click.UsageError("ops must be non-empty.")
    if len(ops) > PROCESS_OPS_MAX:
        raise click.UsageError(f"too many ops; max {PROCESS_OPS_MAX}.")
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise click.UsageError(f"ops[{i}] must be an object.")
        op_type = op.get("op")
        if op_type not in VALID_PROCESS_OPS:
            raise click.UsageError(
                f"ops[{i}].op invalid: {op_type!r}. Valid: {', '.join(sorted(VALID_PROCESS_OPS))}"
            )
        if op_type in _CREATE_OPS:
            _check_ref(op, i)

        if op_type == "create_process":
            _require(op, i, "name")
        elif op_type in ("update_process", "delete_process", "duplicate_process"):
            _require(op, i, "id")
        elif op_type == "create_phase":
            _require(op, i, "name")
            has_process = op.get("process_id") not in (None, "")
            has_parent = op.get("parent_type_id") not in (None, "")
            if has_process == has_parent:
                raise click.UsageError(
                    f"ops[{i}] (create_phase): exactly one of process_id "
                    "(top-level phase) or parent_type_id (objective subprocess "
                    "phase) is required."
                )
        elif op_type in ("update_phase", "delete_phase"):
            _require(op, i, "id")
        elif op_type == "create_phase_row":
            _require(op, i, "phase_id")
        elif op_type in ("update_phase_row", "delete_phase_row"):
            _require(op, i, "id")
        elif op_type == "create_deliverable_type":
            _require(op, i, "phase_id", "name")
        elif op_type in ("update_deliverable_type", "delete_deliverable_type"):
            _require(op, i, "id")
        elif op_type == "set_dependencies":
            _require(op, i, "type_id")
            if not isinstance(op.get("dependency_ids"), list):
                raise click.UsageError(
                    f"ops[{i}] (set_dependencies): dependency_ids must be a list."
                )
        elif op_type == "set_owner_roles":
            _require(op, i, "type_id")
            roles = op.get("role_ids")
            names = op.get("role_names")
            if roles is None and names is None:
                raise click.UsageError(
                    f"ops[{i}] (set_owner_roles): role_ids or role_names is required."
                )
            if roles is not None and not isinstance(roles, list):
                raise click.UsageError(f"ops[{i}] (set_owner_roles): role_ids must be a list.")
            if names is not None and not isinstance(names, list):
                raise click.UsageError(f"ops[{i}] (set_owner_roles): role_names must be a list.")


# --------------------------------------------------------------------------
# get_process assembly — mirrors _assemble_process in the MCP tool.
# --------------------------------------------------------------------------


def _fetch_all_types(client: ExpedaitClient) -> list[dict]:
    out: list[dict] = []
    skip = 0
    for _ in range(TYPES_MAX_PAGES):
        page = client.list_deliverable_types(skip=skip, limit=TYPES_PAGE_SIZE) or []
        items = page if isinstance(page, list) else page.get("items", [])
        out.extend(items)
        if len(items) < TYPES_PAGE_SIZE:
            break
        skip += TYPES_PAGE_SIZE
    return out


def _process_in_use_count(client: ExpedaitClient, process_id: int) -> int:
    """Count projects instantiated from this process, short-circuiting at the
    first match — the delete guard only needs to know the count is non-zero."""
    skip = 0
    count = 0
    for _ in range(PROJECTS_MAX_PAGES):
        page = client.list_projects(skip=skip, limit=PROJECTS_PAGE_SIZE) or []
        items = page if isinstance(page, list) else page.get("items", [])
        count += sum(
            1 for p in items
            if isinstance(p, dict) and p.get("project_type_id") == process_id
        )
        if count > 0:
            return count
        if len(items) < PROJECTS_PAGE_SIZE:
            break
        skip += PROJECTS_PAGE_SIZE
    return count


def _assemble_process(client: ExpedaitClient, process_id: int) -> dict:
    process = client.get_process_type(process_id)
    phases = client.get_process_phases(process_id) or []
    rows = client.get_process_rows(process_id) or []
    roles = client.list_roles() or []
    all_types = _fetch_all_types(client)

    phase_ids = {p["id"] for p in phases}
    role_name = {r["id"]: r.get("name") for r in roles}

    rows_by_phase: dict = {}
    for r in rows:
        rows_by_phase.setdefault(r.get("phase_id"), []).append(r)
    for lst in rows_by_phase.values():
        lst.sort(key=lambda r: (r.get("position") if r.get("position") is not None else 0.0))

    types_by_phase: dict = {}
    for t in all_types:
        if t.get("phase_id") in phase_ids:
            types_by_phase.setdefault(t["phase_id"], []).append(t)
    for lst in types_by_phase.values():
        lst.sort(key=lambda t: (t.get("col_position") if t.get("col_position") is not None else 0.0))

    subphases_by_owner: dict = {}
    for p in phases:
        owner = p.get("parent_deliverable_type_id")
        if owner is not None:
            subphases_by_owner.setdefault(owner, []).append(p)
    for lst in subphases_by_owner.values():
        lst.sort(key=lambda p: (p.get("order") if p.get("order") is not None else 0))

    def build_type(t: dict, depth: int) -> dict:
        owner_role_ids = t.get("owner_role_ids") or []
        card = {
            "id": t.get("id"),
            "name": t.get("name"),
            "abbreviation": t.get("abbreviation"),
            "is_objective": t.get("is_objective", False),
            "parent_type_id": t.get("parent_type_id"),
            "phase_id": t.get("phase_id"),
            "phase_row_id": t.get("phase_row_id"),
            "col_position": t.get("col_position"),
            "owner_role_ids": owner_role_ids,
            "owner_roles": [
                {"id": rid, "name": role_name.get(rid)} for rid in owner_role_ids
            ],
            "dependency_ids": t.get("dependency_ids") or [],
        }
        if t.get("is_objective") and depth < MAX_SUBPROCESS_DEPTH:
            sub = subphases_by_owner.get(t["id"], [])
            card["subprocess"] = {"phases": [build_phase(p, depth + 1) for p in sub]}
        return card

    def build_phase(phase: dict, depth: int) -> dict:
        pid = phase["id"]
        return {
            "id": pid,
            "name": phase.get("name"),
            "description": phase.get("description"),
            "order": phase.get("order"),
            "rows": [
                {"id": r.get("id"), "position": r.get("position")}
                for r in rows_by_phase.get(pid, [])
            ],
            "deliverable_types": [
                build_type(t, depth) for t in types_by_phase.get(pid, [])
            ],
        }

    top_phases = sorted(
        (p for p in phases if p.get("project_type_id") == process_id),
        key=lambda p: (p.get("order") if p.get("order") is not None else 0),
    )

    return {
        "process": {
            "id": process.get("id"),
            "name": process.get("name"),
            "description": process.get("description"),
            "icon": process.get("icon"),
        },
        "phases": [build_phase(p, 0) for p in top_phases],
        "roles": [{"id": r.get("id"), "name": r.get("name")} for r in roles],
    }


# --------------------------------------------------------------------------
# write_process execution context — lazy indices for auto-place + role resolve.
# --------------------------------------------------------------------------


class _WriteContext:
    def __init__(self, client: ExpedaitClient):
        self.client = client
        self._types_loaded = False
        self._type_col: dict = {}
        self._phase_max_col: dict = {}
        self._phase_row_count: dict = {}
        self._roles_by_name: dict | None = None
        self._role_names: list[str] = []

    def _ensure_types_loaded(self) -> None:
        if self._types_loaded:
            return
        for t in _fetch_all_types(self.client):
            tid = t.get("id")
            col = t.get("col_position")
            pid = t.get("phase_id")
            if tid is not None:
                self._type_col[tid] = col
            if pid is not None and col is not None:
                cur = self._phase_max_col.get(pid)
                if cur is None or col > cur:
                    self._phase_max_col[pid] = col
        self._types_loaded = True

    def next_col(self, phase_id: int, after_resolved: int | None) -> float:
        self._ensure_types_loaded()
        if after_resolved is not None:
            anchor = self._type_col.get(after_resolved)
            if anchor is not None:
                return anchor + COL_STEP / 2.0
        cur = self._phase_max_col.get(phase_id)
        new_col = (cur + COL_STEP) if cur is not None else COL_STEP
        self._phase_max_col[phase_id] = new_col
        return new_col

    def register_new_type(self, type_id: int, phase_id: int, col: float) -> None:
        self._type_col[type_id] = col
        cur = self._phase_max_col.get(phase_id)
        if cur is None or col > cur:
            self._phase_max_col[phase_id] = col

    def next_row_position(self, phase_id: int) -> float:
        n = self._phase_row_count.get(phase_id, 0) + 1
        self._phase_row_count[phase_id] = n
        return ROW_STEP * n

    def _ensure_roles_loaded(self) -> None:
        if self._roles_by_name is not None:
            return
        self._roles_by_name = {}
        for r in self.client.list_roles() or []:
            name = r.get("name")
            if name:
                self._roles_by_name[name.strip().lower()] = r.get("id")
                self._role_names.append(name)

    def resolve_role(self, token, refs: RefResolver) -> int:
        # ints and @refs resolve like any id; bare strings are role names.
        if isinstance(token, str) and not token.startswith("@"):
            self._ensure_roles_loaded()
            rid = (self._roles_by_name or {}).get(token.strip().lower())
            if rid is None:
                hint = (
                    "pass a role id, or one of these names: " + ", ".join(sorted(self._role_names))
                    if self._role_names
                    else "create the role first via `roles create`"
                )
                raise OpError("unknown_role", f"no role named {token!r}", fix_hint=hint)
            return rid
        return refs.resolve(token, kind="role_id")


def _put_fields(op: dict, fields) -> dict:
    return {f: op[f] for f in fields if op.get(f) is not None}


def _build_handlers(client: ExpedaitClient, ctx: _WriteContext) -> dict:
    # ---- process ----
    def h_create_process(op, refs):
        payload = {"name": op["name"]}
        payload.update(_put_fields(op, ("description", "instructions", "icon")))
        body = client.create_process(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_update_process(op, refs):
        pid = refs.resolve(op["id"], kind="process id")
        body = client.update_process(pid, _put_fields(op, ("name", "description", "instructions", "icon")))
        return {"id": pid, "name": (body or {}).get("name")}, pid

    def h_duplicate_process(op, refs):
        pid = refs.resolve(op["id"], kind="process id")
        body = client.duplicate_process(pid)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_delete_process(op, refs):
        pid = refs.resolve(op["id"], kind="process id")
        if not op.get("confirm_in_use"):
            in_use = _process_in_use_count(client, pid)
            if in_use:
                raise OpError(
                    "delete_in_use",
                    f"process {pid} has {in_use} project(s) using it",
                    fix_hint="pass confirm_in_use=true to delete it anyway",
                    projects_using=in_use,
                )
        client.delete_process(pid)
        return {"id": pid, "deleted": True}, pid

    # ---- phases ----
    def h_create_phase(op, refs):
        payload = {"name": op["name"]}
        payload.update(_put_fields(op, ("description", "order")))
        if op.get("process_id") not in (None, ""):
            payload["project_type_id"] = refs.resolve(op["process_id"], kind="process_id")
        else:
            payload["parent_deliverable_type_id"] = refs.resolve(
                op["parent_type_id"], kind="parent_type_id",
            )
        body = client.create_phase(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_update_phase(op, refs):
        pid = refs.resolve(op["id"], kind="phase id")
        body = client.update_phase(pid, _put_fields(op, ("name", "description", "order")))
        return {"id": pid, "name": (body or {}).get("name")}, pid

    def h_delete_phase(op, refs):
        pid = refs.resolve(op["id"], kind="phase id")
        client.delete_phase(pid)
        return {"id": pid, "deleted": True}, pid

    # ---- rows ----
    def h_create_phase_row(op, refs):
        phase_id = refs.resolve(op["phase_id"], kind="phase_id")
        position = op.get("position")
        if position is None:
            position = ctx.next_row_position(phase_id)
        body = client.create_phase_row(phase_id, position)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        return {"id": new_id, "position": position}, new_id

    def h_update_phase_row(op, refs):
        rid = refs.resolve(op["id"], kind="row id")
        # position is the only mutable field; a missing one is a no-op error, not
        # a crash. (Preflight only guarantees `id`, so guard here.)
        if op.get("position") is None:
            raise OpError(
                "missing_field", "update_phase_row requires position",
                fix_hint="pass a numeric position to move the row",
            )
        body = client.update_phase_row(rid, op["position"])
        return {"id": rid, "position": (body or {}).get("position")}, rid

    def h_delete_phase_row(op, refs):
        rid = refs.resolve(op["id"], kind="row id")
        client.delete_phase_row(rid)
        return {"id": rid, "deleted": True}, rid

    # ---- deliverable types (cards) ----
    def h_create_deliverable_type(op, refs):
        phase_id = refs.resolve(op["phase_id"], kind="phase_id")
        payload = {"name": op["name"], "phase_id": phase_id}
        payload.update(_put_fields(op, (
            "abbreviation", "description", "instructions", "template_content",
            "deliverable_requirements", "allow_multiple", "is_objective",
        )))
        if op.get("parent_type_id") not in (None, ""):
            payload["parent_type_id"] = refs.resolve(op["parent_type_id"], kind="parent_type_id")
        if op.get("phase_row_id") not in (None, ""):
            payload["phase_row_id"] = refs.resolve(op["phase_row_id"], kind="phase_row_id")
        col = op.get("col_position")
        if col is None:
            after = op.get("after_type_id")
            after_resolved = (
                refs.resolve(after, kind="after_type_id") if after not in (None, "") else None
            )
            col = ctx.next_col(phase_id, after_resolved)
        payload["col_position"] = col
        body = client.create_deliverable_type(payload)
        new_id = body.get("id") if isinstance(body, dict) else None
        refs.bind(op.get("ref"), new_id)
        if new_id is not None:
            ctx.register_new_type(new_id, phase_id, col)
        return {"id": new_id, "name": (body or {}).get("name")}, new_id

    def h_update_deliverable_type(op, refs):
        ttid = refs.resolve(op["id"], kind="deliverable type id")
        payload = _put_fields(op, (
            "name", "abbreviation", "description", "instructions",
            "template_content", "deliverable_requirements", "allow_multiple",
            "is_objective", "col_position",
        ))
        if op.get("phase_id") not in (None, ""):
            payload["phase_id"] = refs.resolve(op["phase_id"], kind="phase_id")
        if op.get("phase_row_id") not in (None, ""):
            payload["phase_row_id"] = refs.resolve(op["phase_row_id"], kind="phase_row_id")
        if op.get("parent_type_id") not in (None, ""):
            payload["parent_type_id"] = refs.resolve(op["parent_type_id"], kind="parent_type_id")
        body = client.update_deliverable_type(ttid, payload)
        return {"id": ttid, "name": (body or {}).get("name")}, ttid

    def h_delete_deliverable_type(op, refs):
        ttid = refs.resolve(op["id"], kind="deliverable type id")
        if not op.get("confirm_in_use"):
            impact = client.get_deliverable_type_usage_impact(ttid) or {}
            total = impact.get("total_deliverables", 0)
            if total:
                raise OpError(
                    "delete_in_use",
                    f"deliverable type {ttid} has {total} instance(s) "
                    f"across {impact.get('projects_using', 0)} project(s)",
                    fix_hint="pass confirm_in_use=true to delete it and its instances",
                    total_deliverables=total,
                    projects_using=impact.get("projects_using", 0),
                )
        client.delete_deliverable_type(ttid)
        return {"id": ttid, "deleted": True}, ttid

    # ---- edges + roles ----
    def h_set_dependencies(op, refs):
        ttid = refs.resolve(op["type_id"], kind="deliverable type id")
        dep_ids = [refs.resolve(d, kind="dependency type id") for d in op["dependency_ids"]]
        client.set_deliverable_type_dependencies(ttid, dep_ids)
        return {"id": ttid, "dependency_ids": dep_ids}, ttid

    def h_set_owner_roles(op, refs):
        ttid = refs.resolve(op["type_id"], kind="deliverable type id")
        tokens = op.get("role_ids")
        if tokens is None:
            tokens = op.get("role_names") or []
        role_ids = [ctx.resolve_role(tok, refs) for tok in tokens]
        client.set_deliverable_type_owner_roles(ttid, role_ids)
        return {"id": ttid, "role_ids": role_ids}, ttid

    return {
        "create_process": h_create_process,
        "update_process": h_update_process,
        "duplicate_process": h_duplicate_process,
        "delete_process": h_delete_process,
        "create_phase": h_create_phase,
        "update_phase": h_update_phase,
        "delete_phase": h_delete_phase,
        "create_phase_row": h_create_phase_row,
        "update_phase_row": h_update_phase_row,
        "delete_phase_row": h_delete_phase_row,
        "create_deliverable_type": h_create_deliverable_type,
        "update_deliverable_type": h_update_deliverable_type,
        "delete_deliverable_type": h_delete_deliverable_type,
        "set_dependencies": h_set_dependencies,
        "set_owner_roles": h_set_owner_roles,
    }


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


@click.group()
def processes() -> None:
    """Inspect and adapt processes (the Process Designer template layer)."""


@processes.command("list")
@click.pass_context
def list_processes(ctx: click.Context) -> None:
    """List processes (project types) in the workspace."""
    client = _make_client(ctx)
    try:
        data = client.list_processes()
    finally:
        client.close()

    fmt = ctx.obj.get("fmt")
    if fmt == "json" or (fmt is None and not is_tty()):
        output(data, "json")
        return
    rows = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "icon": p.get("icon") or "",
            "description": p.get("description") or "",
        }
        for p in data
    ]
    output(rows, "text")


@processes.command("get")
@click.argument("process_id", type=int)
@click.pass_context
def get_process(ctx: click.Context, process_id: int) -> None:
    """Show a process's full template tree (phases, rows, cards, roles)."""
    client = _make_client(ctx)
    try:
        data = _assemble_process(client, process_id)
    finally:
        client.close()
    output(data, ctx.obj.get("fmt"))


@processes.command("write")
@click.option("--ops", "ops_arg", required=True, help="JSON ops array: @file.json, - (stdin), or inline.")
@click.pass_context
def write_process(ctx: click.Context, ops_arg: str) -> None:
    """Build or adapt a process in one call (mirrors write_process).

    Ops chain across entity kinds via named refs: a create op carries ref="x",
    later ops reference "@x". Layout is optional (omit col_position and cards
    auto-place). Deletes refuse an in-use template unless confirm_in_use=true.
    """
    raw = read_value_arg(ops_arg)
    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--ops is not valid JSON: {exc}")
    if not isinstance(ops, list):
        raise click.UsageError("--ops must be a JSON array of op objects.")
    _preflight_validate(ops)

    client = _make_client(ctx)
    wctx = _WriteContext(client)
    try:
        results, affected = run_ops(ops, _build_handlers(client, wctx))
    finally:
        client.close()
    render_ops(ctx, results, affected, affected_key="affected_ids")
