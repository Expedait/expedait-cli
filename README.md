# Expedait CLI

[![PyPI](https://img.shields.io/pypi/v/expedait-cli)](https://pypi.org/project/expedait-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

CLI for [Expedait](https://expedait.org) — lets AI coding agents download project specs and post comments via the Expedait API.

## The model

Expedait organizes specs around four primitives:

- **Objectives** — top-level goals. An objective is itself a deliverable that nests child deliverables beneath it (`parent_deliverable_id`).
- **Deliverables** — the individual spec documents (formerly "pages").
- **Context** — the assembled LLM context for one deliverable: dependency deliverables, linked external sources, uploaded files, and aggregate sizes.
- **Review** — scoring findings raised on a deliverable: severity, description, the criteria that flagged them, and anchor offsets.

## Usage

### Run with `uvx` (recommended)

No installation needed — run directly:

```bash
uvx expedait-cli auth login
uvx expedait-cli projects list
uvx expedait-cli projects download 1
```

### Add as a dev dependency

If your AI agent needs it available in the project environment:

```bash
uv add --group dev expedait-cli
```

Then reference it in your agent configuration (e.g. `CLAUDE.md`, `.cursor/rules`, etc.).

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
expedait projects download PROJECT_ID        # Extract all deliverables to .expedait/context/
expedait projects download PROJECT_ID --output-dir ./specs  # Extract to a custom directory
```

### Deliverables

```bash
expedait deliverables list --project-id PROJECT_ID   # List deliverables in a project
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

### Objectives

```bash
expedait objectives overview DELIVERABLE_ID   # Objective metadata + full descendant tree
```

### Context

```bash
expedait context get DELIVERABLE_ID           # The LLM context snapshot for one deliverable
```

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

## License

[Apache License 2.0](LICENSE)
