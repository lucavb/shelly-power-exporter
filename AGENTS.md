# AGENTS.md

Instructions for AI coding agents working on this repository.

## Setup

```bash
uv sync --dev
```

## Code Style

- Python 3.14+ with type hints
- Line length: 100 characters
- Formatter: ruff
- Linter rules: E, F, I, UP, B, SIM (see pyproject.toml)

Run before committing:
```bash
uv run ruff check .
uv run ruff format .
uv run pyright
```

## Testing

No test suite currently. CI runs linting, type checking, and Docker build verification.

## Build

```bash
# Local run
SHELLY_HOST=<ip> uv run shelly-power-exporter

# Docker
docker build -t shelly-power-exporter:test .
```

## Architecture Notes

- Single-file modules in root directory (no src/ layout)
- All Prometheus metrics defined in metrics.py with `shelly_` namespace
- Device communication via aioshelly RpcDevice (async)
- Multi-channel devices handled by iterating `switch:N` keys in device status
- Version derived from git tags via setuptools-scm

## PR Guidelines

- Commit messages should follow conventional commits style
- CI must pass (ruff check, ruff format --check, pyright, docker build)
