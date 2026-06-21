# Development

[← Docs index](./README.md)

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest
.venv/bin/showbible --help
```

Requires Python 3.11+.

## Tests

Tests live in `tests/` and run under `pytest`. Asyncio auto mode is enabled (see
`pyproject.toml`) for the Textual Pilot smoke tests that drive the TUI.

```bash
.venv/bin/python -m pytest
```

## Smoke run

A quick end-to-end check using the deterministic mock provider:

```bash
.venv/bin/showbible init /tmp/showbible-demo
.venv/bin/showbible run --vault /tmp/showbible-demo --episode S01E01 --provider mock
.venv/bin/showbible status --vault /tmp/showbible-demo
.venv/bin/showbible attach --vault /tmp/showbible-demo --once
```

## Project layout

See [Architecture](./architecture.md) for the module map and extension points. The
short version:

- `showbible/` — the package (`cli`, `engine`, `providers`, `vault`, `server`,
  `artifacts`, `tui/`, `ui/`)
- `tests/` — pytest suite
- `pyproject.toml` — packaging, console scripts (`showbible`, `bible`), pytest config
- `docs/` — this documentation

## Conventions

- Standard-library-first; the only runtime dependency is `textual`.
- All vault writes go through the atomic helpers in `vault.py`
  (`atomic_write_text` / `atomic_write_json`).
- The vault on disk is the source of truth — every interface reads and writes the same
  files.
