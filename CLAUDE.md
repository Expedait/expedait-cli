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

## Style

- Python 3.11+, no type-checker configured
- Use Click for CLI commands, httpx for HTTP calls
- Output defaults to `text` (terminal) or `json` (piped)
