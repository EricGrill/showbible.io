# Interfaces

[← Docs index](./README.md)

ShowBible has three front-ends — CLI, terminal UI, and a local web UI. All three read
and write the **same vault files**, so you can mix and match freely.

## CLI

Granular, scriptable commands for direct control. See the full
[command reference](./cli-reference.md). Add `--json` to many commands for
machine-readable output. Most administrative commands (`cast`, `arcs`, `lore`) print a
sensible default view when run with no subcommand.

In-CLI help is available per topic:

```bash
showbible help                # list topics
showbible help workflow       # cast, episodes, arcs, roles, ai, tui, lore, workflow
```

## TUI (terminal dashboard)

```bash
cd Sopranos
showbible tui --episode S01E01     # alias: showbible workflow
```

A persistent [Textual](https://textual.textualize.io/) dashboard that stays open until
you press `q`. From it you can:

- Create or select episodes (`[` / `]` to switch the selected episode)
- Add show-level or episode-level cast, and apply AI cast suggestions
- Add arc beats and lore facts
- Run the selected episode — this opens a **live phase screen** showing the current
  phase, completed/skipped phases, and model-wait status
- Run `doctor`
- **View/edit outputs** — open the episode's pitch, beats, drafts, script, callbacks,
  and transcript inside the dashboard

| Key | Action |
|---|---|
| `↑/↓` or `k/j` | Move |
| `enter` | Run command / apply |
| `[` / `]` | Switch selected episode |
| `space` | Toggle selection in pickers |
| `a` | Select all in pickers |
| `q` | Cancel / quit |

In a non-interactive shell (or with `--no-tui`), the same command prints a minimum
first-episode checklist instead of opening the UI.

## Web UI

```bash
showbible attach --vault . --port 8765      # then open the printed http://127.0.0.1:8765
showbible attach --vault . --once           # print a JSON smoke payload and exit
```

A loopback-only HTTP server served straight from the Python package. It **rejects any
non-loopback host** (only `127.0.0.1`, `localhost`, `::1` are allowed) for safety. It
exposes each episode's artifacts as editable tabs — Pitch, Beats, drafts, Script,
Callbacks, and transcript — with a **Save** button, plus an intervention box.

JSON API routes:

| Route | Purpose |
|---|---|
| `GET /api/status` | Vault status: cast, episodes, doctor findings, cost |
| `GET /api/episode?episode=S01E01` | Episode artifact payload |
| `GET /api/artifact` | Read a single artifact |
| `POST /api/artifact` | Save a single artifact |
| `GET /api/transcript?episode=S01E01` | Concatenated writers-room transcript |
| `POST /api/intervene` | Append a producer note / guest-writer intervention |
