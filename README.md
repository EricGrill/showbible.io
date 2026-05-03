# ShowBible

ShowBible is a local-first AI writers room framework. It stores show packs,
episode outputs, transcripts, lore, and runtime state in a git-friendly
markdown vault.

This repository currently contains the first v0 vertical slice:

- `showbible init <path>` scaffolds a vault.
- `showbible run --provider mock` generates a deterministic episode pipeline.
- `showbible status`, `doctor`, `transcript`, `lore`, `arcs`, and `cost`
  inspect the vault.
- `showbible attach` serves a loopback-only web UI from the Python package.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest
.venv/bin/showbible --help
```

## Smoke Run

```bash
.venv/bin/showbible init /tmp/showbible-demo
.venv/bin/showbible run --vault /tmp/showbible-demo --episode S01E01 --provider mock
.venv/bin/showbible status --vault /tmp/showbible-demo
.venv/bin/showbible attach --vault /tmp/showbible-demo --once
```
