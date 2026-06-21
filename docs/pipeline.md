# The episode pipeline

[← Docs index](./README.md)

`showbible run` walks an episode through six fixed phases. Each phase calls the
provider once, records the exchange in the writers-room transcript (attributed to the
most relevant cast member), and writes a concrete artifact file.

```mermaid
flowchart LR
    subgraph inputs[Context fed to each phase]
        pack[pack.yaml]
        intervene[notes / speak-as]
    end

    start([showbible run]) --> resume{Artifact<br/>exists?}
    resume -- yes --> skip[skip phase]
    resume -- no --> p1

    p1[1 · pitch] --> p2[2 · break] --> p3[3 · fast-draft]
    p3 --> p4[4 · room-pass] --> p5[5 · polish] --> p6[6 · continuity-check]

    p1 -. pitch.md .-> art1[(episode files)]
    p2 -. beats.md .-> art1
    p3 -. drafts/v1-fast.md .-> art1
    p4 -. drafts/room-pass-notes.md .-> art1
    p5 -. script.md + v2-after-room.md .-> art1
    p6 -. callbacks.yaml .-> art1
    p6 == appends ==> canon[lore-bible/canon.md]

    pack -.-> p1
    intervene -.-> p1
    p6 --> done([RunResult: phases, tokens, cost])
```

| # | Phase | Goal | Artifact(s) |
|---|---|---|---|
| 1 | `pitch` | One-paragraph pitch tied to the season theme | `pitch.md` |
| 2 | `break` | Turn the pitch into act beats / scene spine | `beats.md` |
| 3 | `fast-draft` | Compact screenplay-style dialogue for the core scene | `drafts/v1-fast.md` |
| 4 | `room-pass` | Writers-room notes flagging weak character/theme choices | `drafts/room-pass-notes.md` |
| 5 | `polish` | Integrate notes into a clean script excerpt | `drafts/v2-after-room.md`, `script.md` |
| 6 | `continuity-check` | Check continuity, name new canon, stay concise | `callbacks.yaml` (+ appends to `lore-bible/canon.md`) |

## Resumability

The run is resumable. Before running, ShowBible inspects which artifacts already exist
(and are non-empty) and skips those phases. Re-running an episode only fills in the
missing phases. Later phases receive earlier artifacts (pitch, beats) plus the pack and
any interventions as context.

To run every existing episode in one go (or create `S01E01` if none exist):

```bash
showbible run --season
```

## Interventions

Interventions let a human steer the room mid-pipeline:

```bash
showbible run --episode S01E01 \
  --note "Keep it under five scenes; the antagonist never appears on screen." \
  --speak-as "carmela:I want a scene where she almost tells the truth and stops."
```

- `--note <text>` injects a producer note.
- `--speak-as <slug>:<text>` voices a specific character.

Both are appended to the writers-room transcript and persisted in the episode's
`meta.json`, so they survive across resumed runs. The web UI's intervention box does
the same thing via `POST /api/intervene`.

## Run output

`run` reports completed/skipped phase counts and token usage, and updates the cost
ledger (`.room/costs.json`, viewable with `showbible cost`). Note that cost is
currently recorded as `$0.00` for every provider — see [Limitations](./architecture.md#limitations).
