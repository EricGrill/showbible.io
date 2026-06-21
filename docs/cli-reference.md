# Command reference

[← Docs index](./README.md)

Run `showbible help` for in-CLI topic help (`cast`, `episodes`, `arcs`, `roles`, `ai`,
`tui`, `lore`, `workflow`). Most commands accept `--vault <path>`; without it, the
vault is discovered by walking up from the current directory.

The console command is available as both `showbible` and `bible`.

## Vault & lifecycle

```bash
showbible init <dir> [--from "Show Name"] [--force]   # scaffold a vault
showbible status [--json]                             # cast/episode counts + doctor summary
showbible doctor [--json]                             # integrity check (exit 4 on errors)
showbible pause | resume                              # mark room paused/running
showbible continue [--episode ID] [--provider P]      # run the next/current episode
showbible cost [--json]                               # token & dollar ledger
showbible attach [--host H] [--port N] [--once]       # local web UI (loopback only)
```

## Episodes

```bash
showbible episode new [ID]            # default S01E01
showbible episode list
showbible episode show ID [--json]    # status, completed phases, cast, arcs
showbible episode fork ID [TARGET]    # deep-copy an episode (records forked_from)
showbible run --episode ID [--season] [--provider P] [--note ...] [--speak-as ...]
showbible transcript [ID]             # print the writers-room transcript
```

`run --season` runs every existing episode (or creates `S01E01` if none exist).
`--speak-as` takes a `<character-slug>:<text>` value. See [the pipeline](./pipeline.md)
for what a run does.

## Cast

```bash
showbible cast list [--episode ID | --show]
showbible cast kinds
showbible cast add "Edie Falco" --kind actor --plays carmela [--person SLUG]
showbible cast remove <person-slug>
showbible cast suggest [SHOW] [--episode ID | --show] [--limit N] [--apply] [--pick] [--json]
```

`cast suggest` asks the provider for real public people associated with the show,
excluding the current effective cast. In a real terminal it opens a picker; use
`--apply` to accept all suggestions, `--json` for scripts, or `--pick` to force the
picker. Suggestions are saved to a `cast-suggestions.md` file in the relevant scope.

## Arcs

```bash
showbible arcs [list]                 # list arcs (beat counts)
showbible arcs current [--episode ID] # beats relevant to an episode
showbible arcs show [ARC]             # print an arc file (default season-theme)
showbible arcs add "Pilot tests the season theme" [--arc A] [--episode ID] [--status S]
showbible arcs suggest [--arc A] [--episode ID] [--limit N] [--apply] [--json]
```

## Lore

```bash
showbible lore [show]                 # print canon
showbible lore explain
showbible lore paths                  # list lore file locations
showbible lore add "Tony owes Junior a debt" [--source S01E01]
showbible lore suggest [--episode ID] [--limit N] [--apply] [--json]
```

Lore is currently **append-only canon**: episode continuity-checks and manual/AI facts
all land in `lore-bible/canon.md`.

## Pack

```bash
showbible pack list                    # show vault name
showbible pack add "Show" [--from URL]  # seed a research note
showbible pack edit <person-slug>      # open people/<slug>.md in $EDITOR
showbible pack export                   # the pack is filesystem-native; just share the vault
```

## Exit codes

| Code | Meaning |
|---|---|
| `1` | Generic / OS error |
| `2` | Usage or value error |
| `3` | Vault not found |
| `4` | Integrity error (doctor found errors) |
| `5` | Provider error |
