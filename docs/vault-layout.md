# Vault layout

[← Docs index](./README.md)

`showbible init` scaffolds the following structure. Everything is plain text — commit
the whole vault to git to version your show's history. All writes are atomic
(write-to-temp + `os.replace`).

```
MyShow/
├── pack.yaml                 # the show bible (premise, season, roles, provider, budget)
├── research/
│   ├── sources.md
│   └── notes.md
├── people/                   # one markdown persona per person (YAML frontmatter)
│   ├── showrunner.md
│   ├── director.md
│   └── staff-writer.md
├── lore-bible/
│   ├── canon.md              # ## Facts — append-only canon
│   ├── glossary.md
│   └── relationships.md
├── arcs/
│   └── season-theme.md       # story beats across episodes
├── episodes/
│   └── S01E01/               # created on first run / episode new
│       ├── meta.json         # status, completed_phases, cast_overrides, interventions
│       ├── pitch.md
│       ├── beats.md
│       ├── script.md
│       ├── callbacks.yaml
│       ├── drafts/
│       │   ├── v1-fast.md
│       │   ├── room-pass-notes.md
│       │   └── v2-after-room.md
│       └── writers-room/     # numbered transcript files per phase + interventions
└── .room/
    ├── state.json            # current episode/phase + status
    ├── costs.json            # token/dollar ledger
    ├── sessions/             # per-episode run snapshots
    ├── locks/
    └── interventions/
```

## Key files

- **`pack.yaml`** — the root marker that makes a directory a vault. Holds the show
  premise, season metadata, the show-level `roles` list, provider preference, and
  budget. Cast edits at show scope rewrite the `roles:` section here.
- **`people/<slug>.md`** — a persona with YAML frontmatter (voice fingerprint,
  beliefs, trait axes) and relationship notes. The model adopts these voices.
- **`episodes/<id>/meta.json`** — per-episode run state: `status`, `completed_phases`,
  `phase_events`, `cast_overrides`, and recorded `interventions`.
- **`lore-bible/canon.md`** — canonical facts under a `## Facts` heading; the
  continuity-check phase and `lore add`/`lore suggest --apply` append here.
- **`.room/state.json`** & **`.room/sessions/<id>.json`** — live run status used by the
  TUI's phase screen.

See [Core concepts](./concepts.md) for what each of these represents conceptually.
