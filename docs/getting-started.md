# Getting started

[← Docs index](./README.md)

## Install

ShowBible is a Python package (3.11+). Install it editable into a virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

The install exposes two equivalent console commands: **`showbible`** and **`bible`**.

## Your first show

```bash
# Scaffold a vault for a show
showbible init Sopranos --from "The Sopranos"
cd Sopranos

# Generate a first episode with the deterministic mock provider (no model needed)
showbible run --episode S01E01 --provider mock

# Inspect what was produced
showbible status
showbible transcript S01E01
```

`showbible init` creates a self-contained [vault](./vault-layout.md) — a directory of
plain markdown/JSON files describing one show.

## Using a real model

To generate with a real local model instead of the mock, start
[LM Studio](https://lmstudio.ai/) (default endpoint `http://127.0.0.1:1234`) and drop
`--provider mock`:

```bash
showbible run --episode S01E01
```

See [Providers & configuration](./providers.md) for model selection and environment
variables.

## End-to-end smoke run

```bash
showbible init /tmp/showbible-demo
showbible run --vault /tmp/showbible-demo --episode S01E01 --provider mock
showbible status --vault /tmp/showbible-demo
showbible attach --vault /tmp/showbible-demo --once
```

## Where to next

- [Core concepts](./concepts.md) — vault, pack, cast, arcs, lore
- [The episode pipeline](./pipeline.md) — what `run` actually does
- [Interfaces](./interfaces.md) — CLI, terminal UI, web UI
- [Command reference](./cli-reference.md) — every command and flag
