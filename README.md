# Expedait CLI

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Command-line interface for [Expedait](https://expedait.com) — download project specs and post comments from AI coding agents.

## Quickstart

```bash
# Install with uv (recommended)
uv pip install expedait-cli

# Or install from source
git clone https://github.com/Expedait/expedait-cli.git
cd expedait-cli
uv sync

# Login to your Expedait instance
expedait auth login

# List your projects
expedait projects list

# Download all specs for a project
expedait projects download 1 --output-dir ./specs
```

## Installation

### From PyPI

```bash
pip install expedait-cli
```

### From source

```bash
git clone https://github.com/Expedait/expedait-cli.git
cd expedait-cli
uv sync
```

This creates a virtual environment with the `expedait` command available.

**Requirements:** Python 3.11+

## Authentication

### Interactive login

```bash
expedait auth login
```

Prompts for API URL, email, and password. Stores credentials in `~/.expedait/config.json`.

### Environment variables (CI / agents)

```bash
export EXPEDAIT_TOKEN="your-jwt-token"
export EXPEDAIT_API_URL="https://your-instance.expedait.com"
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
expedait projects download PROJECT_ID               # Download all pages as ZIP
expedait projects download PROJECT_ID --output-dir ./specs  # Extract to directory
```

### Pages

```bash
expedait pages list --project-id PROJECT_ID         # List pages in a project
expedait pages get PAGE_ID                          # Print page markdown content
expedait pages full PAGE_ID                         # Full context (content + comments + deps)
expedait pages download PAGE_ID --output-dir ./out  # Download page as ZIP
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

## Global Options

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

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
