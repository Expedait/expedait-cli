# Expedait CLI

[![PyPI](https://img.shields.io/pypi/v/expedait-cli)](https://pypi.org/project/expedait-cli/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

CLI for [Expedait](https://expedait.org) — lets AI coding agents download project specs and post comments via the Expedait API.

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
expedait pages list                     # no --project-id needed
expedait pages download 42              # downloads to .expedait/context/
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
expedait projects list                              # List all projects
expedait projects get PROJECT_ID                    # Get project details
expedait projects download PROJECT_ID               # Extract markdown to .expedait/context/
expedait projects download PROJECT_ID --download-format json  # Download as JSON
expedait projects download PROJECT_ID --output-dir ./specs    # Extract to custom directory
```

### Pages

```bash
expedait pages list --project-id PROJECT_ID         # List pages in a project
expedait pages get PAGE_ID                          # Print page markdown content
expedait pages full PAGE_ID                         # Full context (content + comments + deps)
expedait pages download PAGE_ID                     # Extract markdown to .expedait/context/
expedait pages download PAGE_ID --download-format json  # Download as JSON
```

### Comments

```bash
expedait comments list PAGE_ID                      # List comments on a page
expedait comments create PAGE_ID \                  # Create a comment
  --text "Comment content" \
  --selected-text "text from page" \
  --start-offset 100 \
  --end-offset 120 \
  --source-page-id 5                                # Optional: agent's source page
expedait comments resolve PAGE_ID COMMENT_ID        # Mark as resolved
expedait comments delete PAGE_ID COMMENT_ID         # Delete a comment
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
