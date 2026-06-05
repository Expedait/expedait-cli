# Changelog

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
