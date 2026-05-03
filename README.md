# ShowBible

ShowBible is a local-first AI writers room framework. It stores show packs,
episode outputs, transcripts, lore, and runtime state in a git-friendly
markdown vault.

This repository currently contains the first v0 vertical slice:

- `showbible init <path>` scaffolds a vault.
- `showbible run --provider mock` generates a deterministic episode pipeline.
- `showbible workflow` / `showbible tui` guide first-episode setup.
- `showbible status`, `doctor`, `transcript`, `lore`, `arcs`, and `cost`
  inspect the vault.
- `showbible attach` serves a loopback-only web UI from the Python package.
- The default provider is LM Studio at `http://127.0.0.1:1234` using
  `google/gemma-4-e4b`; pass `--provider mock` for deterministic local tests.
  Override with `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL`, or
  `LMSTUDIO_MAX_TOKENS`.

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

## CLI-Only Show Dashboard

For the minimum first-episode path, start the persistent dashboard:

```bash
cd /tmp/showbible-demo
showbible tui --episode S01E01
```

The dashboard stays open until you press `q`. From there you can create or
select episodes, add show-level cast, add episode cast overrides, apply AI cast
suggestions, add arc beats, add lore facts, run the selected episode, and run
doctor. Running an episode opens a live phase screen so you can see the current
phase, skipped/completed phases, and model-wait status instead of staring at a
silent terminal. `View/edit outputs` opens the selected episode's pitch, beats,
drafts, script, callbacks, and transcript files in the TUI. `showbible workflow
--episode S01E01 --no-tui` prints the same minimum checklist for scripts and
noninteractive shells.

The web UI exposes the same episode output artifacts as tabs with an editor and
Save button:

```bash
showbible attach --vault /tmp/showbible-demo --port 8765
```

The lower-level commands are still available when you want direct CLI control:

```bash
cd /tmp/showbible-demo
showbible cast list
showbible cast add "Patrick Stewart" --kind actor --plays picard
showbible cast suggest
showbible cast suggest --apply
showbible pack edit patrick-stewart
```

Cast commands infer scope from the current folder:

```bash
cd /tmp/showbible-demo
showbible cast add "David Chase" --kind showrunner       # show-level pack cast

cd /tmp/showbible-demo/episodes/S01E03
showbible cast add "Steve Buscemi" --kind director       # episode-only override
showbible cast suggest --apply                           # episode-only AI suggestions
showbible cast add --show "Edie Falco" --kind actor      # force show-level from episode cwd
showbible cast add --episode S01E05 "Guest Star"         # force a specific episode
```

Discover the administration surface from the CLI:

```bash
showbible help
showbible help cast
showbible help episodes
showbible help arcs
showbible help roles
showbible help lore
showbible help workflow
showbible cast kinds
showbible episode show S01E01
```

`showbible cast suggest` excludes the current effective cast. In a real terminal
it opens a picker; use `--json` for scripts, or `--apply` to accept all returned
suggestions.

Lore is markdown-first:

```bash
showbible lore
showbible lore explain
showbible lore paths
showbible lore add "Tony owes Junior a debt" --source S01E01
```

Arcs are command-driven too:

```bash
showbible arcs
showbible arcs current --episode S01E01
showbible arcs add "Pilot establishes the central argument" --episode S01E01
showbible arcs show season-theme
```
