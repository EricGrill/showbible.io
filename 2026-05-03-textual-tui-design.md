---
title: Textual TUI dashboard
status: draft
date: 2026-05-03
supersedes: 2026-05-03-tui-dashboard-restructure-design.md
---

## Problem

The current `showbible tui` is a hand-rolled `curses` dashboard. Every long-running call (Run, AI suggest) blocks the entire screen because the redraw loop, the input loop, and the work all live on one thread. Live state (cast roster, arc beats, lore, doctor findings) only refreshes after explicit actions or pressing `r`. The previously-specced curses cleanup ([2026-05-03-tui-dashboard-restructure-design.md](2026-05-03-tui-dashboard-restructure-design.md)) reorganises the menu but inherits the same architectural ceiling.

## Goal

Replace the curses dashboard with a Textual app that:

- Keeps the user navigating freely while AI generation, episode runs, and other background work happen.
- Reflects vault changes within ~1 second without manual refresh — including changes made by other terminals or editors.
- Supports unlimited concurrent episode runs, each with its own progress stream.
- Picks up the original cleanup intent (NAVIGATE: Episodes/Cast/Arc/Lore/Outputs · COMMAND: Run/Snapshot/Doctor/Quit) for free, since rewriting the shell is the right place to do it.
- Bundles the framework-neutral foundation work (vault mutators for arcs/lore, `arcs suggest` / `lore suggest` CLI commands) so the new panes have library functions to call instead of shelling argparse.

Out of scope (deferred to later phases): WebSocket/NATS/Redis transports, an async-aware engine, run cancellation, web UI changes, custom theming, token-level streaming.

## Architecture

A single Textual app boots from `showbible tui`, fully replacing the curses entry. It reuses the existing sync `engine.run_episode`, `providers.*`, and `vault.*` modules unchanged. Long calls (Run, AI suggest) dispatch via Textual's `@work(thread=True)` decorator — the worker runs in a thread, the UI stays interactive on the asyncio event loop. A 1s `set_interval` re-reads vault state into a single reactive `AppState`; Textual's `watch` mechanism re-renders any pane bound to changed fields.

**New runtime dep:** `textual>=0.86` (pulls `rich` transitively). Added to `[project] dependencies` in `pyproject.toml`.

**No new transports** — the entire Phase 2 scope stays in-process. WebSockets/NATS/Redis are Phase 3/4.

## Module layout

```
showbible/
  tui/                       ← new package; replaces curses helpers in cli.py
    __init__.py
    app.py                   # ShowBibleApp(textual.App) — root, owns AppState
    state.py                 # AppState (reactive), snapshot builder
    runs.py                  # RunHandle, RunRegistry, progress callback bridge
    panes/
      __init__.py
      episodes.py            # EpisodesPane
      cast.py                # CastPane
      arc.py                 # ArcPane
      lore.py                # LorePane
      outputs.py             # OutputsPane (Rich preview + edit-in-$EDITOR)
      run_detail.py          # RunDetailPane (visible while a run is in flight)
    screens/
      __init__.py
      add_cast.py            # ModalScreen — Cast add/edit
      add_arc_beat.py        # ModalScreen — Arc beat add/edit
      add_lore.py            # ModalScreen — Lore fact add/edit
      ai_suggest.py          # ModalScreen — generic LoadingIndicator + SelectionList
      confirm.py             # Small yes/no modal for delete
      snapshot.py            # ModalScreen — Static text dump from _workflow_snapshot_text
      doctor.py              # ModalScreen — list of DoctorFinding rows
    widgets/
      __init__.py
      sidebar.py             # NAVIGATE/COMMAND list + active-runs tail
      run_status.py          # Footer "Running S01E0X (3/6)" row
      entity_form.py         # Reusable form layout for the three Add modals
```

## App shell

A single `Screen` with three regions, plus modal overlays pushed on demand:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ShowBible · <show> · vault: <path> · <episode> (<status>)           │  Header
├──────────────┬──────────────────────────────────────────────────────┤
│ NAVIGATE     │                                                      │
│   Episodes   │                                                      │
│   Cast       │              CONTENT PANE                            │
│   Arc        │   (one of EpisodesPane/CastPane/ArcPane/LorePane/    │
│   Lore       │    OutputsPane/RunDetailPane)                        │
│   Outputs    │                                                      │
│              │                                                      │
│ COMMAND      │                                                      │
│   Run S01E01 │                                                      │
│   Snapshot   │                                                      │
│   Doctor     │                                                      │
│   Quit       │                                                      │
│              │                                                      │
│ ACTIVE RUNS  │                                                      │
│   ● S01E02   │                                                      │
│   (3/6)      │                                                      │
├──────────────┴──────────────────────────────────────────────────────┤
│ ⏎ run · [/] episode · r refresh · q quit · Last: <message>          │  Footer
└─────────────────────────────────────────────────────────────────────┘
```

- **Header** — `Static`. Reactive to `AppState.show_name`, `vault`, `current_episode`, `episode_status`.
- **Sidebar** — `Sidebar` widget, three sections: NAVIGATE, COMMAND, ACTIVE RUNS. Each section is an `OptionList`. Selecting a NAVIGATE item swaps the content pane via `Pane.show()`. Selecting a COMMAND item triggers an action: Run dispatches a worker; Snapshot opens `SnapshotScreen` (a `ModalScreen` showing the multi-line text returned by `_workflow_snapshot_text` in a `Static` with a Close button); Doctor opens `DoctorScreen` (modal listing the `DoctorFinding` records, or "All clean." if none); Quit exits. ACTIVE RUNS rows render reactively from `AppState.runs`; selecting one switches the content pane to `RunDetailPane` filtered to that run.
- **Default content pane on boot** — `EpisodesPane` (the user's first navigation interest in nearly all sessions). Sidebar cursor starts on the Episodes row.
- **Footer** — Textual's built-in `Footer` for hotkey hints + a `RunStatus` widget showing the latest `last_action` toast (auto-clears after ~5s).

## Pane behavior

Every navigation pane uses the same `Horizontal` shape: a list/table on the left, a detail pane on the right. Hotkeys are pane-scoped via Textual `Binding`s.

| Pane | Rows | Detail | Hotkeys |
|------|------|--------|---------|
| **Episodes** | each episode + `+ New episode` | meta (status, completed phases, cast overrides count) | `n` new, `Enter` select, `f` fork |
| **Cast** | each effective role with `[ep]` / `[sh]` tag, kind, display name, plays + `+ Add` | role detail + `people/<slug>.md` path | `a` add, `e` edit, `d` delete, `s` AI suggest |
| **Arc** | every beat across every arc (`[arc] EP [status] text`) + `+ Add` | beat detail (arc, episode, status, text, `arcs/<arc>.md` path) | `a` add, `e` edit, `d` delete, `s` AI suggest |
| **Lore** | each canon fact + `+ Add` | fact text, source, `lore-bible/canon.md` path | `a` add, `e` edit, `d` delete, `s` AI suggest |
| **Outputs** | each artifact (pitch.md, beats.md, drafts/v1-fast.md, …) | Rich-rendered markdown preview | `e` open in `$EDITOR` (suspend → resume), `r` refresh preview |

Add/edit hotkeys push the corresponding `ModalScreen` (`AddCastScreen`, `AddArcBeatScreen`, `AddLoreScreen`). On submit the modal calls the matching vault helper and dismisses with the operation's status string, which the pane writes to `AppState.last_action`. Delete pushes `ConfirmScreen` first.

The `s` (AI suggest) hotkey pushes the generic `AISuggestScreen` modal. Phase 1 of the modal shows a `LoadingIndicator` with a label like `Generating arc beat suggestions…` while a `@work(thread=True)` task runs the relevant `_generate_*_suggestions` function. Phase 2 (after the worker returns) replaces the indicator with a `SelectionList` (multi-select with checkboxes); Enter applies via the matching `_apply_*_suggestions`, Esc cancels. This is the spinner-then-picker pattern from the existing `_cast_suggest_tui`, but Textual-native.

## Run lifecycle (concurrent)

Triggering `Run S01E0X` from COMMAND dispatches a `@work(thread=True)` worker that calls `engine.run_episode(vault, episode_id, provider, progress=...)`. The `progress` callback (called from the worker thread) pushes events onto the app via `app.call_from_thread(...)`, which the asyncio loop drains into `RunRegistry`.

```python
@dataclass
class RunHandle:
    run_id: str          # uuid4 hex slice
    episode_id: str
    started_at: float
    current_phase: str | None
    completed_phases: list[str]
    skipped_phases: list[str]
    tokens: int
    dollars: float
    status: str          # "running" | "complete" | "failed"
    error: str | None
    log_tail: deque[str] # last 100 lines (left-evicted)
```

`RunRegistry` is a thin `dict[str, RunHandle]` exposed reactively on `AppState.runs`.

Multiple runs may be in flight simultaneously (per the unlimited-concurrency decision). The sidebar's ACTIVE RUNS section renders one row per `RunHandle` with a `●` glyph and `EP (k/6)` summary. Selecting a row swaps the content pane to `RunDetailPane`, which shows the phase checklist (`[x] pitch / [>] break / [ ] fast-draft / …`) and the `log_tail` for that run.

When a run finishes, the `RunHandle.status` flips to `complete`/`failed`, the sidebar row turns to a dim `✓` / `✗` for ~5s and then disappears, and a footer toast prints the summary (`S01E0X complete · 6 phases · 12.4k tokens · $0.00`).

**No cancellation in this iteration.** `engine.run_episode` is sync and not interrupt-safe. App teardown calls `worker.cancel()` which signals the thread but waits for the current phase to finish. Adding mid-phase cancel requires Phase 1 (async-aware engine).

## State / data model

A single reactive `AppState` owned by `ShowBibleApp`:

```python
class AppState(Reactive):
    vault: Path
    show_name: str
    current_episode: str
    episodes: list[str]
    cast: list[CastRole]              # effective for current_episode
    arc_beats: list[ArcBeat]
    lore_facts: list[LoreFact]
    doctor_findings: list[DoctorFinding]
    costs: dict
    last_action: str
    runs: dict[str, RunHandle]
```

Two refresh paths keep it current:

1. **Timer poll** — `set_interval(1.0)` calls `AppState.refresh_from_disk()`, which re-reads `list_episodes`, `effective_cast_roles`, `arc_beats`, `lore_facts`, `doctor`, `costs` from disk. Cheap (a handful of small markdown reads). Picks up edits from other terminals or editors.
2. **Action-triggered** — every vault mutation (Add Cast, Add Beat, Add Fact, etc.) calls `AppState.refresh_from_disk()` synchronously after the helper returns, so the user sees their change immediately rather than at the next tick.

Panes bind to slices of state with the `watch_<field>` pattern — when `arc_beats` changes the Arc pane's table repopulates; nothing else re-renders.

## Forms

A single `EntityForm` widget pattern is reused by all three Add/Edit modals:

```
┌─ Add cast member ─────────────────┐
│ Display name: [______________]    │
│ Kind:         [actor          ▾]  │
│ Plays:        [______________]    │
│ Scope:        ( ) show (•) episode│
│                                   │
│              [Cancel]  [Save]     │
└───────────────────────────────────┘
```

- `Tab`/`Shift+Tab` cycle fields.
- `Enter` on the last field submits.
- `Esc` cancels.
- Each modal returns a typed payload (`CastFormResult`, `ArcBeatFormResult`, `LoreFactFormResult`); the dispatching pane calls the matching vault helper and updates `AppState.last_action`.
- Edit-mode reuses the same modal with fields pre-filled.

## Foundation work bundled in

The Textual panes need helpers and CLIs that don't exist yet. This spec includes them:

**Vault helpers** (in `showbible/vault.py`):
- `arc_beats(vault) -> list[ArcBeat]` — already shipped (commit `5101ad2`).
- `add_arc_beat`, `update_arc_beat`, `remove_arc_beat`.
- `lore_facts(vault) -> list[LoreFact]` (+ `LoreFact` dataclass).
- `add_lore_fact`, `update_lore_fact`, `remove_lore_fact`.
- `cmd_arcs_add` and `cmd_lore_add` refactored to call the helpers (CLI surface unchanged).

**AI suggest CLI commands** (in `showbible/cli.py`):
- `_generate_arc_suggestions` + `cmd_arcs_suggest` + `arcs suggest` subparser.
- `_generate_lore_suggestions` + `cmd_lore_suggest` + `lore suggest` subparser.
- `--apply` and `--json` modes only — no `--pick`. The Textual `AISuggestScreen` covers the interactive pick path; the curses-based `_pick_suggestions` extraction proposed in the prior plan is dropped.
- The TUI `s` hotkey calls the same `_generate_*_suggestions` functions directly.

## What gets deleted

Removed from `showbible/cli.py` (~600 LOC purged):
- `_workflow_tui`, `_dashboard_actions`, `_run_dashboard_action`, `_run_dashboard_live`, `_format_run_event`, `_draw_run_progress`, `_dashboard_panel_lines`, `_dashboard_prompt`, `_prompt_dashboard_line`.
- `_episodes_tui`, `_cast_tui`, `_episode_outputs_tui`, `_arc_tui`/`_lore_tui` stubs (whether already added or pending), `_arc_suggest_tui`, `_lore_suggest_tui`, `_cast_suggest_tui`, `_pick_items_screen`, `_pick_cast_suggestions`.
- `import curses`, `import threading` (the threading uses move into `tui/runs.py`).

`cmd_tui` shrinks to (mirroring the existing `cmd_workflow` shape):

```python
def cmd_tui(args):
    vault = resolve_vault(args.vault)
    episode_id = args.episode or _current_episode(vault) or "S01E01"
    ensure_episode(vault, episode_id)
    _write_room_state(vault, "planning", episode_id=episode_id)
    if args.no_tui or not (sys.stdin.isatty() and sys.stdout.isatty()):
        _print_workflow_snapshot(vault, episode_id, args.provider)
        return 0
    from showbible.tui.app import ShowBibleApp
    return ShowBibleApp(vault, episode_id, args.provider).run()
```

`cmd_workflow` collapses to the same body (the two have always been near-duplicates) or becomes a thin alias; the implementer should pick one and delete the other.

## Error handling

- **Worker exception during Run** — caught in the worker wrapper; `RunHandle.status` set to `"failed"`, `RunHandle.error` populated, footer toast prints `S01E0X failed: <message>`. Other runs continue.
- **Worker exception during AI suggest** — `AISuggestScreen` swaps from `LoadingIndicator` to a small error panel showing the message + a Close button.
- **Vault helper raises `VaultError`** — modal captures and shows inline; the form stays open with the user's input intact so they can fix and retry.
- **Disk I/O errors during the timer poll** — caught at the boundary in `AppState.refresh_from_disk`, a one-shot toast warns ("Vault read failed: <message>"); the previous snapshot stays in place so the UI doesn't blank.
- **`$EDITOR` not set or returns non-zero** — Outputs pane shows toast and stays on the preview.

## Testing

**Unit tests** (`tests/test_showbible.py`):
- Vault helpers — round-trip add → list → update → remove for both arcs and lore (covers preservation of unrelated lines in the source files).
- `cmd_arcs_add` / `cmd_lore_add` after refactor — output and on-disk format byte-identical to today.
- `_generate_arc_suggestions` / `_generate_lore_suggestions` — happy path with stub provider, `ProviderError` fallback that exercises the static seed list.
- `AppState.refresh_from_disk` — populates expected fields from a fixture vault.

**Pilot smoke tests** (`tests/test_tui_smoke.py`):
- Boot the app against a fixture vault; assert sidebar shows NAVIGATE + COMMAND items as expected.
- Navigate to each of Episodes/Cast/Arc/Lore/Outputs; assert each mounts without raising and renders ≥ one row when fixture data is present.
- Open the Add Cast modal, fill it, submit; assert a new row appears in the Cast pane.
- Trigger `Run S01E01` with `--provider mock`; assert the sidebar Active Runs row appears, then disappears within ~3s; assert `RunHandle.status == "complete"`.
- Open the AI Suggest modal for Arc with the mock provider; assert it transitions from indicator to selection list.

All ~5 Pilot tests run via `async def` + `app.run_test()`.

## Migration / data

No on-disk format changes. Vault layout stays identical. Only the dashboard process changes shape.

## Out of scope (explicit, do not implement)

- WebSocket / NATS / Redis transports (Phase 3/4).
- Async-aware engine + run cancellation tokens (Phase 1 prerequisite).
- Updates to `showbible/server.py` or `ui/index.html` — the existing HTTP+poll web UI keeps working untouched.
- Token-level streaming during phases (engine doesn't expose it; phase boundaries are the granularity).
- Custom CSS / theming beyond Textual's default.
- Multi-vault switching inside the app (still one vault per process).
