---
title: TUI dashboard restructure — nouns vs. commands
status: superseded
superseded_by: 2026-05-03-textual-tui-design.md
date: 2026-05-03
---

> **Superseded.** The curses cleanup proposed here was abandoned in favour of a full Textual rewrite. See [2026-05-03-textual-tui-design.md](2026-05-03-textual-tui-design.md). The framework-neutral pieces (vault helpers for arcs/lore, `arcs suggest` / `lore suggest` CLI commands) are absorbed into the new spec.


## Problem

The `showbible tui` dashboard currently mixes navigation entries (sub-screens) with one-shot inline prompts in a single flat menu:

```
Show snapshot
Manage episodes        ← sub-screen
Manage cast            ← sub-screen
Add S01E01 arc beat    ← inline prompt
Add S01E01 lore fact   ← inline prompt
View/edit S01E01 outputs
Run S01E01
Doctor
Quit
```

The two "Add …" rows are operational verbs hiding inside a list of nouns; arcs and lore have no place to view, edit, delete, or AI-suggest their entries the way Cast does. The menu reads as ad-hoc rather than logical.

## Goal

Reorganize the menu so it reads as: navigate to a noun (which opens a managed sub-screen), or invoke a command (run/doctor/snapshot). Bring Arc and Lore to feature parity with Cast — list, add, edit, delete, AI suggest — all reached through the same two-pane sub-screen pattern.

Out of scope: visual restyling, web UI changes, changes to the right-hand status panel, episode workflow phases, provider configuration.

## Dashboard menu

Two labelled sections separated by a blank menu row. Up/down arrows skip across the blank.

```
NAVIGATE
  Episodes
  Cast
  Arc
  Lore
  Outputs

COMMAND
  Run S01E01
  Snapshot
  Doctor
  Quit
```

Notes:
- Section headers (`NAVIGATE`, `COMMAND`) render as non-selectable bold rows.
- The `Run` and `Outputs` rows continue to interpolate the selected episode id (`Run S01E01`, etc.).
- Existing top-line hotkeys remain: `enter` activate, `[`/`]` step episode, `r` refresh, `q` quit.
- The right-hand status panel (`_dashboard_panel_lines`) is unchanged.

Removed from the top-level menu (relocated, not deleted):
- `Show snapshot` → renamed `Snapshot`, moved into COMMAND.
- `Add {episode} arc beat` → moved inside the Arc sub-screen as the `+ Add new beat` row + `a` hotkey.
- `Add {episode} lore fact` → moved inside the Lore sub-screen as `+ Add new fact` row + `a` hotkey.
- `Manage episodes` → renamed `Episodes`.
- `Manage cast` → renamed `Cast`.
- `View/edit {episode} outputs` → renamed `Outputs`.

## Sub-screens

All sub-screens follow the established two-pane pattern from `_cast_tui`:
- Left pane: list of items (capped at the available row count) with a final `+ Add new …` row.
- Right pane: detail view of the selected item.
- Top line: title (`Arc — <vault>`, `Lore — <vault>`).
- Second line: hotkey hint.
- `q` or ESC returns to the dashboard with a status message.

### Arc sub-screen — `_arc_tui(screen, vault, episode_id, provider)`

Flat list of every beat across every arc in `vault/arcs/*.md`.

Left pane row format: `[arc-slug] S01E01 [status] beat text…` (truncated to menu width). Final row: `+ Add new beat`.

Right pane fields:
- `arc:` arc slug
- `episode:` episode id
- `status:` planned/in-progress/done/etc.
- `beat:` full beat text (wrapped)
- `file:` `arcs/<slug>.md`

Hotkeys:
- `j`/`k` or arrows — move
- `a` — add: prompts arc slug (default `season-theme`), episode id (default current), status (default `planned`), beat text. Calls `add_arc_beat` vault helper.
- `e` — edit: prompts the four fields pre-filled with the current beat's values. Calls `update_arc_beat`.
- `d` — delete: confirmation prompt, then `remove_arc_beat`.
- `s` — AI suggest: opens `_arc_suggest_tui`, which mirrors the existing `_cast_suggest_tui`. It runs `_generate_arc_suggestions` on a background thread while drawing a spinner (`Generating suggestions… |/-\`), then hands the result to the in-TUI picker `_pick_items_screen` so the user can select which beats to apply.
- `q`/ESC — return.

### Lore sub-screen — `_lore_tui(screen, vault, episode_id, provider)`

Flat list of facts from `vault/lore-bible/canon.md`.

Left pane row format: the fact text, truncated to menu width. Final row: `+ Add new fact`.

Right pane fields:
- `fact:` full fact text (wrapped)
- `source:` source recorded by `cmd_lore_add` (parsed from the trailing `*Source: <value>*` marker on each `- **Manual fact** - …` bullet), defaulting to `manual`
- `file:` `lore-bible/canon.md`

Hotkeys: same letters as Arc (`a`, `e`, `d`, `s`, `q`), backed by the lore vault helpers and `_generate_lore_suggestions`. The `s` hotkey opens `_lore_suggest_tui` — same spinner + `_pick_items_screen` flow as the Arc and Cast equivalents.

### Episodes, Cast, Outputs

Unchanged. Their menu labels are simplified ("Episodes" rather than "Manage episodes") but the underlying TUIs (`_episodes_tui`, `_cast_tui`, `_episode_outputs_tui`) keep their current behavior.

## Vault helpers

Add to `showbible/vault.py` so the TUI calls library functions instead of going through argparse:

Arcs:
- `arc_beats(vault) -> list[ArcBeat]` — flat list across all arc files. `ArcBeat` is a dataclass with `arc`, `episode`, `status`, `beat`, `file`.
- `add_arc_beat(vault, arc_slug, episode_id, status, beat) -> Path` — extracts the existing append logic from `cmd_arcs_add`.
- `update_arc_beat(vault, arc_slug, episode_id, original_beat, *, new_episode_id, new_status, new_beat) -> Path` — locates the matching `- S01E0X [status] beat` line and rewrites it.
- `remove_arc_beat(vault, arc_slug, episode_id, beat_text) -> Path` — locates and removes the matching line.

Lore:
- `lore_facts(vault) -> list[LoreFact]` — parsed from the `## Facts` bullets in `lore-bible/canon.md`. Each bullet today has the shape `- **Manual fact** - <text> *Source: <source>*`; the parser strips the `**Manual fact** -` prefix and the trailing `*Source: …*` marker. `LoreFact` carries `text`, `source`.
- `add_lore_fact(vault, text, source) -> Path` — extracts the append logic from `cmd_lore_add`.
- `update_lore_fact(vault, original_text, *, new_text, new_source) -> Path`.
- `remove_lore_fact(vault, fact_text) -> Path`.

Refactor `cmd_arcs_add` and `cmd_lore_add` to call the new helpers. CLI surface and output stay byte-identical.

## AI suggest commands

New CLI commands and shared generator functions, structured to mirror `cmd_cast_suggest` / `_generate_cast_suggestions`.

`_generate_arc_suggestions(vault, episode_id, provider, limit=6, arc_slug='season-theme') -> list[dict]`:
- Reads `vault/pack.yaml` for show context.
- Reads existing beats for the arc to seed exclusions.
- Prompts the model for up to `limit` JSON objects with keys `episode`, `status`, `beat`.
- Saves raw output to `episodes/<id>/arc-suggestions-raw.md` on parse failure (matches cast pattern).
- Falls back to a small static list on `ProviderError` so dashboards stay usable offline.

`_generate_lore_suggestions(vault, episode_id, provider, limit=6) -> list[dict]`:
- Same shape; returns objects with `fact` (and optional `source`).

CLI:
- `showbible arcs suggest [--episode] [--arc] [--provider] [--limit] [--apply|--pick|--json]`
- `showbible lore suggest [--episode] [--provider] [--limit] [--apply|--pick|--json]`

Both follow the cast precedent: `--apply` writes immediately, `--pick` opens the curses picker (terminal-only), default prints JSON and saves the suggestion file.

The TUI `s` hotkey routes through dedicated `_arc_suggest_tui` / `_lore_suggest_tui` helpers (parallel to the existing `_cast_suggest_tui`). They run the model on a background thread, draw a `Generating suggestions… |/-\` spinner so the user can see work is in flight, and on completion delegate to the in-TUI picker `_pick_items_screen` to let the user choose which suggestions to apply.

## Data flow

```
dashboard menu (Episodes/Cast/Arc/Lore/Outputs/Run/Snapshot/Doctor/Quit)
  ├── enter on NAVIGATE row → opens corresponding *_tui sub-screen
  │     sub-screen → vault helper functions → arcs/lore/cast/episodes files on disk
  └── enter on COMMAND row → existing dashboard action (run/snapshot/doctor/quit)
```

No changes to the engine, providers, or web server.

## Error handling

- Empty arc/lore lists: left pane shows only the `+ Add new …` row with the cursor on it.
- Edit/delete with no item selected (cursor on the add row): the `e`/`d` keys are no-ops.
- AI suggest provider failure: same as cast — raw response is saved beside the suggestion file, status message reports the path.
- Vault helper write failures: surface as the screen's status message on return; do not crash the TUI.

## Testing

Add to `tests/`:
- Unit tests for each new vault helper (round-trip add → list → update → remove for both arcs and lore; covers preservation of unrelated lines in the source files).
- Tests that `cmd_arcs_add` / `cmd_lore_add` still produce the same file contents after the refactor.
- Tests that `_dashboard_actions` returns the new ordered structure (NAVIGATE rows, blank, COMMAND rows) for a representative episode id.
- `_generate_arc_suggestions` and `_generate_lore_suggestions` tested with a stub provider that returns canned JSON, plus a `ProviderError` path that exercises the fallback.

The TUI screens themselves are not unit-tested today (curses); follow that precedent and rely on the underlying helpers being covered.

## Migration

Pure additive in storage terms — same on-disk file shapes for arcs and lore. The only user-visible change is the dashboard menu structure and the new sub-screens. No vault migration script needed.
