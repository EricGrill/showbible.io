# ShowBible

**ShowBible is a local-first AI "writers room" framework for episodic television and
screenwriting.** It drives a language model through a structured, multi-phase
episode-writing pipeline while keeping everything — the show pack, cast, lore, story
arcs, generated drafts, transcripts, and runtime state — in a plain, git-friendly
markdown vault on your disk. No cloud database, no lock-in: the vault is just files you
can read, edit, diff, and commit.

> **Status:** v0 alpha (a working vertical slice). The pipeline, CLI, terminal UI, and
> local web UI are functional against a local model or a deterministic mock. Remote
> provider hooks (Anthropic/OpenAI/Ollama) are stubs, and cost tracking currently
> records `$0.00`. See [Limitations](./docs/architecture.md#limitations).

## Quick start

```bash
# Install (editable, into a virtualenv)
python3 -m venv .venv
.venv/bin/python -m pip install -e .

# Scaffold a vault and generate a first episode (no model needed with --provider mock)
.venv/bin/showbible init Sopranos --from "The Sopranos"
cd Sopranos
showbible run --episode S01E01 --provider mock
showbible status
```

To use a real local model, start [LM Studio](https://lmstudio.ai/) and drop
`--provider mock`. The install exposes two equivalent commands: **`showbible`** and
**`bible`**.

→ Full walkthrough in [Getting started](./docs/getting-started.md).

## Documentation

| Doc | What's inside |
|---|---|
| [Getting started](./docs/getting-started.md) | Install, scaffold a vault, generate a first episode |
| [Core concepts](./docs/concepts.md) | Vault, pack, people, cast, arcs, lore, scope |
| [The episode pipeline](./docs/pipeline.md) | The six phases, diagram, resumability, interventions |
| [Interfaces](./docs/interfaces.md) | CLI, terminal UI, and local web UI |
| [Command reference](./docs/cli-reference.md) | Every command, flag, and exit code |
| [Providers & configuration](./docs/providers.md) | LM Studio, mock, env vars, fallbacks, adding a provider |
| [Vault layout](./docs/vault-layout.md) | On-disk structure and key files |
| [Architecture](./docs/architecture.md) | Module map, data flow, extension points, limitations |
| [Development](./docs/development.md) | Setup, tests, smoke run, conventions |

## What it does, in one minute

`showbible run` walks an episode through six phases — **pitch → break → fast-draft →
room-pass → polish → continuity-check** — calling the model once per phase and writing
a real artifact each time (`pitch.md`, `beats.md`, drafts, `script.md`,
`callbacks.yaml`). Runs are resumable (existing artifacts are skipped) and steerable
with producer notes and per-character `--speak-as` interventions. The same vault is
reachable from the CLI, a Textual terminal dashboard, and a loopback-only web UI.

See [the pipeline](./docs/pipeline.md) for the full flow diagram.

## License

MIT © Eric Grill
