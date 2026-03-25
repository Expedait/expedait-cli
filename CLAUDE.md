# CLAUDE.md

## Project

Expedait CLI — a Python CLI (Click + httpx) for downloading project specs and posting comments via the Expedait API.

## Build & Run

```bash
uv sync                      # install deps
uv sync --group dev          # install with dev deps
uv run expedait --help       # run the CLI
```

## Test

```bash
uv run python -m pytest      # run all tests
uv run python -m pytest tests/test_auth.py  # run a single file
```

## Code Layout

- `expedait_cli/` — source: `main.py` (Click entrypoint), `client.py` (httpx API client), `auth.py`, `config.py`, `formatters.py`, `commands/` (Click subcommands)
- `tests/` — pytest tests using `pytest-httpx` for mocking HTTP

## Versioning

When creating a PR, bump the patch version in `pyproject.toml` (the `version` field) and include that change in the PR.

To publish a release, push a git tag matching the version (e.g. `git tag v0.2.1 && git push origin v0.2.1`). This triggers CI to publish to PyPI and create a GitHub Release with auto-generated notes listing the PRs since the previous tag.

## Style

- Python 3.11+, no type-checker configured
- Use Click for CLI commands, httpx for HTTP calls
- Output defaults to `text` (terminal) or `json` (piped)
