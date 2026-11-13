# AGENTS.md

Instructions for AI coding agents working on this repository.

## Setup and checks

Requires Python 3.15 or newer. Install development dependencies with:

```bash
uv sync --dev
```

Run the same checks as CI:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
docker build -t shelly-power-exporter:test .
```

## Architecture

- Python modules are at the repository root; `main.py` runs the async polling lifecycle.
- `collector.py` extracts readings from Shelly RPC status; `metrics.py` publishes snapshots
  through the Prometheus HTTP server.
- `config.py` reads environment settings; `version.py` obtains the version from setuptools-scm.
- Device communication uses `aioshelly`'s async `RpcDevice`; switch components use `switch:N`
  status keys.
