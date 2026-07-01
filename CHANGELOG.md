# Changelog

## 0.4.3

Close the last gap with the hosted MCP server's write surface: the CLI can now
create, update, and delete **projects** (instances of a process), not just list
and download them. This mirrors the MCP `write_project` tool — every other MCP
write tool already had a CLI counterpart.

### Added
- **Project writes** (mirror MCP `write_project`): `projects create --name …
  --process-id …`, `projects update PROJECT_ID …`, `projects delete PROJECT_ID`,
  and a `projects write --ops` batch (`create_project` / `update_project` /
  `delete_project`) with `$last` / `@ref` chaining. Ergonomic subcommands each
  compose one op through the shared ops engine, so output and error handling
  match `write --ops`.
- **Two-step delete guard**: deleting a project cascades to every deliverable,
  version, file, comment, and agent run and is irreversible. The REST endpoint
  has no server-side confirm, so the CLI enforces one — a bare `projects delete
  PROJECT_ID` previews the cascade and deletes nothing; `--confirm` (or a
  `delete_project` op carrying `"confirm": true`) is required to actually delete.

## 0.4.2

Repository governance ahead of the project going public. No runtime behavior
changes.

### Added
- **`.github/CODEOWNERS`**: require review from a maintainer on every change.
- **`SECURITY.md`**: private vulnerability disclosure policy.
- **`.github/dependabot.yml`**: weekly `uv` and `github-actions` update PRs.

## 0.4.1

Packaging and documentation polish ahead of the repository going public. No
runtime behavior changes.

### Changed
- **PyPI metadata**: added `authors`, `keywords`, trove `classifiers`, and
  `[project.urls]` (Homepage, Repository, Issues, Changelog) so the PyPI project
  page links back to the repo and the package is discoverable in search.
- **README**: added a Table of Contents; restructured install docs into an
  `Installation` section with multiple methods (`uvx`, `uv tool install`,
  `pipx`, `pip`) leading with isolated installers; added a `Quickstart` with a
  `--help` discoverability note; added `Getting Help` and `Contributing`
  sections.

## 0.4.0

Bring the CLI to parity with the hosted MCP server's write surface — agents can
now create and adapt content, processes, and roles, not just read them. Every
new command supports `--format json` and reports a per-op summary.

### Added
- **Deliverable writes** (mirror MCP `write_deliverable`):
  - `deliverables write --ops @file.json` — ordered batch of `create` / `edit` /
    `rename` / `save_version` / `set_state` ops, chainable with `id="$last"` or
    named refs (`ref="x"` on create, `id="@x"` later). Pre-flight validates op
    shape and reference ordering; ops stop on first failure (rest `skipped`) and
    the command exits non-zero on partial failure.
  - Ergonomic subcommands on top: `deliverables create`, `edit`, `rename`,
    `save-version`, `set-state` (states: Not Started, In Progress, Review,
    Approved, Completed, Final). `--content` / `--instructions` accept `@file`,
    `-` (stdin), or a literal.
- **`processes` command group** (mirror MCP `list_processes` / `get_process` /
  `write_process`): `processes list`, `processes get PROCESS_ID` (full template
  tree — phases, rows, deliverable-type cards, owner roles, objective
  subprocesses), and `processes write --ops` (create/update/delete process,
  phases, rows, deliverable types; `set_dependencies`; `set_owner_roles`). Named
  refs, optional card layout with auto-placement (`after_type_id` / append),
  role-name resolution, and an in-use delete guard (`confirm_in_use`).
- **`roles` command group** (mirror MCP `list_roles` / `write_role`):
  `roles list`, `roles create`, `roles update`, `roles delete`, and
  `roles write --ops`.
- **Context-file management** under the `context` group — manage the uploaded
  files that feed a deliverable's (or objective's) LLM context: `context files`
  (list), `context add` (upload; re-upload by name replaces), `context
  file-content` (parsed text), `context download-file`, `context remove-file`,
  and `context set-file --exclude/--include` (toggle a file in/out of the LLM
  context). External source links remain web-app integration flows.
- `expedait_cli/ops.py` — shared multi-op engine (`RefResolver`, `run_ops`,
  `render_ops`) behind all three write surfaces, mirroring the MCP server's
  `_common.py` run-ops scaffold.
- `client.BackendError` + an op-safe request path so per-op failures are
  captured and reported instead of aborting the whole command.
- `deliverables types` — list deliverable types so you can find the `--type` id
  that `deliverables create` needs.
- `projects workspace [PROJECT_ID]` — deliverables grouped by phase (mirrors the
  MCP `get_project_workspace` tool); the structure-aware view the flat
  `deliverables list` can't give.

### Fixed
- `processes write` no longer crashes with an uncaught `KeyError` when an
  `update_phase_row` op omits `position`; it now reports a clean per-op
  `missing_field` error.
- `--content` / `--instructions` / `--ops` with a missing or unreadable `@file`
  now raise a clear usage error instead of leaking an `OSError` traceback. The
  three duplicate readers were consolidated into one helper (`ops.read_value_arg`).
- `projects download` no longer crashes. It passed a `fmt=` argument that the
  client method never accepted (a `TypeError` on every run, hidden by a loosely
  mocked test). The backend `/download` endpoint has no format parameter, so the
  dead `--download-format` option was removed; the command always extracts the
  markdown + images ZIP.

## 0.3.0

Adapt the CLI to the product's four-primitive domain model (objectives,
deliverables, context, review).

### Added
- `deliverables` command group (`list`, `get`, `inspect`, `download`) — the
  rename of `pages`, pointed at `/api/v1/deliverables/...`.
- `deliverables get --include` — comma-separated section reads (`meta`,
  `content`, `template`, `requirements`, `writer_instructions`, `dependencies`,
  `external_context`, `score`, `comments`, `versions`), defaulting to `content`.
  `meta` surfaces `parent_deliverable_id`.
- `objectives overview DELIVERABLE_ID` — objective metadata plus its full
  descendant tree.
- `context get DELIVERABLE_ID` — read-only LLM context snapshot for a
  deliverable.
- `review` command group: `review issues DELIVERABLE_ID [--state open|muted|all]`
  and `review mute ISSUE_ID [--note TEXT] [--unmute]`.
- `comments create --agent-run-id` to link a comment to a build run.
- `expedait-cli` console-script alias so `uvx expedait-cli …` keeps working.

### Changed
- `comments create` now resolves anchor offsets from the deliverable content;
  only `--text` and `--selected-text` are required. `--start-offset` /
  `--end-offset` remain available as explicit overrides.
- Renamed `comments create --source-page-id` → `--source-deliverable-id`
  (payload field `source_page_id` → `source_deliverable_id`).
- `comments resolve` / `comments delete` now use the deliverable-scoped routes
  `/api/v1/deliverables/{id}/comments/{comment_id}`.

### Deprecated
- The `pages` command group. `expedait pages …` still works for one release
  (warns and forwards to `deliverables`) and will then be removed.
