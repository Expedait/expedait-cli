# Expedait CLI

[![PyPI](https://img.shields.io/pypi/v/expedait-cli)](https://pypi.org/project/expedait-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

CLI for [Expedait](https://expedait.org) — lets AI coding agents download project specs and post comments via the Expedait API.

## Table of Contents

- [The model](#the-model)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Project Setup](#project-setup)
- [Authentication](#authentication)
- [Commands](#commands)
- [Agent Skills](#agent-skills)
- [Development](#development)
- [Getting Help](#getting-help)
- [Contributing](#contributing)
- [License](#license)

## The model

Expedait organizes specs around four primitives:

- **Objectives** — top-level goals. An objective is itself a deliverable that nests child deliverables beneath it (`parent_deliverable_id`).
- **Deliverables** — the individual spec documents (formerly "pages").
- **Context** — the assembled LLM context for one deliverable: dependency deliverables, linked external sources, uploaded files, and aggregate sizes.
- **Review** — scoring findings raised on a deliverable: severity, description, the criteria that flagged them, and anchor offsets.

## Installation

Requires Python 3.11+.

### Run with `uvx` (recommended)

No install needed — [`uvx`](https://docs.astral.sh/uv/) fetches and runs the CLI on demand, always at the latest version:

```bash
uvx expedait-cli --help
```

With `uvx` you invoke commands as `uvx expedait-cli <command>`. The methods below install an `expedait` executable so you can drop the prefix and run `expedait <command>` (the form used throughout this README).

### Install globally

```bash
uv tool install expedait-cli      # via uv — isolated, recommended
pipx install expedait-cli         # via pipx — isolated
pip install expedait-cli          # via pip
```

`uv tool install` and `pipx` keep the CLI in its own virtual environment so it never conflicts with other Python packages — the recommended way to install a standalone CLI.

### Add as a project dependency

For an AI agent that needs the CLI available in the project environment:

```bash
uv add --group dev expedait-cli
```

Then reference it in your agent configuration (e.g. `CLAUDE.md`, `.cursor/rules`).

## Quickstart

```bash
expedait auth login          # 1. Authenticate (SSO or email/password)
expedait init                # 2. Store tenant + project for this directory
expedait projects download   # 3. Pull all deliverables into .expedait/context/
```

Every command and subcommand supports `--help`:

```bash
expedait --help
expedait deliverables --help
expedait deliverables create --help
```

## Project Setup

After authenticating, run `init` inside your project directory to store your tenant and project settings locally:

```bash
uvx expedait-cli init
```

This creates `.expedait/settings.json` with your `tenant_id` and `project_id`. Add `.expedait/` to your `.gitignore`.

Once initialized, commands that need a project ID will resolve it automatically. Downloads default to `.expedait/context/`:

```bash
expedait projects download              # downloads to .expedait/context/
expedait deliverables list              # no --project-id needed
expedait deliverables download 42       # downloads to .expedait/context/
```

**Resolution order for tenant/project:** CLI flag > env var > `.expedait/settings.json` > `~/.expedait/config.json`.

## Authentication

### Interactive login

```bash
uvx expedait-cli auth login
```

Prompts for login method (SSO or email/password). Stores credentials in `~/.expedait/config.json`.

### Environment variables (CI / agents)

```bash
export EXPEDAIT_TOKEN="your-jwt-token"
export EXPEDAIT_API_URL="https://your-instance.expedait.org"
export EXPEDAIT_TENANT_ID=1
```

**Token resolution order:** `EXPEDAIT_TOKEN` env var > `~/.expedait/config.json` > error.

## Commands

### Auth

```bash
expedait auth login       # Interactive login
expedait auth status      # Show current user and tenant
expedait auth logout      # Clear stored credentials
```

### Projects

```bash
expedait projects list                       # List all projects
expedait projects get PROJECT_ID             # Get project details
expedait projects workspace PROJECT_ID       # Deliverables grouped by phase (structure-aware view)
expedait projects download PROJECT_ID        # Extract all deliverables to .expedait/context/
expedait projects download PROJECT_ID --output-dir ./specs  # Extract to a custom directory
```

### Deliverables

```bash
expedait deliverables list --project-id PROJECT_ID   # List deliverables in a project
expedait deliverables types                           # List deliverable types (find the --type ID for create)
expedait deliverables get DELIVERABLE_ID             # Print deliverable markdown content
expedait deliverables get DELIVERABLE_ID --include meta,content,dependencies,score
expedait deliverables inspect DELIVERABLE_ID         # Full context (content + comments + deps + lock)
expedait deliverables download DELIVERABLE_ID        # Extract to .expedait/context/
```

`--include` accepts a comma-separated subset of: `meta`, `content`, `template`,
`requirements`, `writer_instructions`, `dependencies`, `external_context`,
`score`, `comments`, `versions`. It defaults to `content`. `meta` surfaces
`parent_deliverable_id` (non-null ⇒ this deliverable is a child nested under an
objective).

#### Writing deliverables

Mirrors the MCP `write_deliverable` tool. Ergonomic subcommands cover the common
cases; `write --ops` applies an ordered batch in one call.

```bash
expedait deliverables create --project P --type TYPE_ID --title "Vision" \
  [--content @vision.md] [--parent-deliverable-id ID]   # create (content: @file, - for stdin, or literal)
expedait deliverables edit DELIVERABLE_ID --content @body.md   # replace content (autosave, no version bump)
expedait deliverables rename DELIVERABLE_ID --title "New title" # rename without touching content
expedait deliverables save-version DELIVERABLE_ID --reason "checkpoint"  # explicit snapshot
expedait deliverables set-state DELIVERABLE_ID --state "Review"          # transition workflow state
```

Valid states: `Not Started`, `In Progress`, `Review`, `Approved`, `Completed`,
`Final`.

For multi-step writes, `write --ops` takes a JSON ops array (`@file.json`, `-`
for stdin, or inline). Each op is one of `create`, `edit`, `rename`,
`save_version`, `set_state`. Chain ops on a freshly-created deliverable with
`"id": "$last"` (the previous op's deliverable) or bind a name on create
(`"ref": "x"`) and reference it later as `"id": "@x"`:

```bash
expedait deliverables write --ops @ops.json
# ops.json:
# [
#   {"op": "create", "ref": "v", "project_id": 1, "deliverable_type_id": 3, "title": "Vision"},
#   {"op": "edit", "id": "@v", "content": "# Product Vision\n..."},
#   {"op": "set_state", "id": "@v", "state": "Review"}
# ]
```

Ops run in order and stop on the first failure (the rest report `skipped`); the
output reports per-op `{status: ok | error | skipped}`, and the command exits
non-zero if any op failed.

### Objectives

```bash
expedait objectives overview DELIVERABLE_ID   # Objective metadata + full descendant tree
```

### Context

```bash
expedait context get DELIVERABLE_ID           # The LLM context snapshot for one deliverable
```

A deliverable's (or objective's) context is built from dependency deliverables,
linked external sources, and **uploaded context files**. The CLI manages the
file half of that surface — attach reference docs an agent should write against,
and toggle whether each one feeds the LLM context:

```bash
expedait context files DELIVERABLE_ID                 # List attached context files
expedait context add DELIVERABLE_ID ./reference.md    # Upload a context file (re-upload by name replaces)
expedait context file-content FILE_ID                 # Parsed text the file contributes to context
expedait context download-file FILE_ID -o ./out.md    # Download a file's raw bytes
expedait context set-file FILE_ID --exclude           # Exclude from LLM context (or --include)
expedait context remove-file FILE_ID                  # Delete a context file
```

External source links (Notion, GitHub, etc.) are created through the web app's
integration flows, not the CLI.

### Review

```bash
expedait review issues DELIVERABLE_ID                 # List scoring findings (default: all)
expedait review issues DELIVERABLE_ID --state open    # Only open findings
expedait review mute ISSUE_ID --note "by design"      # Mute a finding
expedait review mute ISSUE_ID --unmute                # Unmute a finding
```

### Comments

```bash
expedait comments list DELIVERABLE_ID                 # List comments on a deliverable
expedait comments create DELIVERABLE_ID \             # Create a comment (offsets resolved automatically)
  --text "Comment content" \
  --selected-text "text from the deliverable" \
  --source-deliverable-id 5                            # Optional: agent's source deliverable
expedait comments resolve DELIVERABLE_ID COMMENT_ID   # Mark as resolved
expedait comments delete DELIVERABLE_ID COMMENT_ID    # Delete a comment
```

Only `--text` and `--selected-text` are required; the CLI locates the selected
text in the deliverable to compute anchor offsets. Pass `--start-offset` and
`--end-offset` to anchor explicitly (e.g. when the selected text appears more
than once).

### Processes (Process Designer)

A *process* is a project type plus the template tree it owns: phases → rows →
deliverable-type cards, dependency edges, owner roles, and objective
subprocesses. Editing it reshapes **every** project instantiated from it.
Mirrors the MCP `list_processes` / `get_process` / `write_process` tools.

```bash
expedait processes list                   # List processes (project types)
expedait processes get PROCESS_ID         # Full template tree (phases, rows, cards, roles)
expedait processes write --ops @ops.json  # Build or adapt a process in one call
```

`write --ops` ops: `create_process`, `update_process`, `duplicate_process`,
`delete_process`, `create_phase`, `update_phase`, `delete_phase`,
`create_phase_row`, `update_phase_row`, `delete_phase_row`,
`create_deliverable_type`, `update_deliverable_type`, `delete_deliverable_type`,
`set_dependencies`, `set_owner_roles`. Ops chain via named refs (`"ref": "x"` on
a create op, `"@x"` later). Card layout is optional — omit `col_position` and
cards auto-place (append, or just after `after_type_id`). `set_owner_roles`
accepts role names or ids. Delete ops refuse an in-use template unless the op
carries `"confirm_in_use": true`.

```jsonc
// ops.json — build a process end to end in one call
[
  {"op": "create_process", "ref": "p", "name": "Product Dev"},
  {"op": "create_phase", "ref": "ph", "process_id": "@p", "name": "Discovery"},
  {"op": "create_deliverable_type", "ref": "vision", "phase_id": "@ph", "name": "Vision"},
  {"op": "create_deliverable_type", "ref": "prd", "phase_id": "@ph", "name": "PRD", "after_type_id": "@vision"},
  {"op": "set_dependencies", "type_id": "@prd", "dependency_ids": ["@vision"]},
  {"op": "set_owner_roles", "type_id": "@prd", "role_names": ["Product Manager"]}
]
```

### Roles

A *role* is a workspace project role — the owner-role pool assigned to
deliverable types. A role's `instructions` is its LLM coaching persona. Mirrors
the MCP `list_roles` / `write_role` tools.

```bash
expedait roles list                                       # List project roles
expedait roles create --name "Product Manager" \          # Create (instructions: @file, -, or literal)
  [--description "owns the roadmap"] [--instructions @pm.md]
expedait roles update ROLE_ID --name "Lead PM"            # Update name/description/instructions
expedait roles delete ROLE_ID                             # Delete a role
expedait roles write --ops @ops.json                      # Batch (create_role/update_role/delete_role)
```

### Global Options

```bash
expedait --api-url https://host:8000 ...    # Override API URL
expedait --tenant-id 2 ...                  # Override tenant
expedait --format json ...                  # Force JSON output
expedait --format text ...                  # Force human-readable output
expedait --version                          # Show version
```

Output format defaults to `text` when connected to a terminal, `json` when piped.

> **Migration note:** the `pages` command group has been renamed to
> `deliverables`. `expedait pages …` still works for one release (it warns and
> forwards) but will be removed.

## Agent Skills

For step-by-step guides on using the CLI from AI coding agents, see [expedait-skills](https://github.com/Expedait/expedait-skills).

## Development

```bash
git clone https://github.com/Expedait/expedait-cli.git
cd expedait-cli
uv sync --group dev
uv run python -m pytest
```

## Getting Help

- Run `expedait <command> --help` for terminal reference on any command.
- Found a bug or have a feature request? [Open an issue](https://github.com/Expedait/expedait-cli/issues).

## Contributing

Contributions are welcome. Set up the project as shown in [Development](#development), make your change with tests, and open a pull request against `main`. CI runs the test suite on Python 3.11–3.13.

## License

[Apache License 2.0](LICENSE)
