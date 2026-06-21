# Core concepts

[← Docs index](./README.md)

| Concept | What it is |
|---|---|
| **Vault** | A directory containing one show. Identified by a `pack.yaml` at its root. ShowBible auto-discovers the vault by walking up from your current directory, or you can pass `--vault <path>`. |
| **Pack** | `pack.yaml` — the show's premise: name, genre, tone, season info, theme, arc spine, default roles, provider preference, and budget. The "bible" the room writes against. |
| **People** | One markdown file per person in `people/`, with YAML frontmatter describing a voice fingerprint, beliefs, and personality trait axes. These are the personas the model adopts. |
| **Cast** | The *roles* people fill (showrunner, director, writer, actor, …). Defined show-wide in `pack.yaml`, and optionally overridden per episode. |
| **Arcs** | Markdown files in `arcs/` tracking story beats across episodes (e.g. `season-theme.md`). |
| **Lore** | The canon bible in `lore-bible/` (`canon.md`, `glossary.md`, `relationships.md`). Continuity-check output is appended to canon automatically. |
| **Episode** | A folder under `episodes/` (e.g. `S01E01/`) holding generated artifacts, a writers-room transcript, and `meta.json` run state. |
| **Room state** | Runtime bookkeeping under `.room/` — current episode/phase, session snapshots, and a cost ledger. |

See the full on-disk structure in [Vault layout](./vault-layout.md).

## Cast roles

Seven role kinds are recognized (`showbible cast kinds`):

| Kind | Responsibility |
|---|---|
| `showrunner` | Leads season taste, theme, and final calls. |
| `director` | Breaks scenes, frames conflict, integrates polish. |
| `writer` | Drafts pitches, beats, dialogue, alternate turns. |
| `actor` | Protects a character voice (use `--plays <character-slug>`). |
| `lore-keeper` | Checks continuity, canon, callbacks, arc consistency. |
| `producer` | Steers constraints, budget, audience, franchise fit. |
| `guest-writer` | Episode-specific outside voice or specialist pass. |

During a run, phases are attributed to the most relevant cast member in the
transcript (e.g. the showrunner pitches, the director breaks beats).

## Scope: show vs episode

**Scope is inferred from your working directory.** At the vault root, cast/arc/lore
commands operate show-wide (editing `pack.yaml`). Inside an episode folder
(`episodes/S01E03/`), the same commands target that episode's overrides. Force scope
explicitly with `--show` or `--episode <id>`.

Episode cast is *effective cast* = show-level roles overlaid with episode overrides
(stored in the episode's `meta.json` under `cast_overrides`). An override replaces a
show-level role for the same person within that episode only.

```bash
cd Sopranos
showbible cast add "David Chase" --kind showrunner       # show-level

cd episodes/S01E03
showbible cast add "Steve Buscemi" --kind director       # episode-only override
showbible cast add --show "Edie Falco" --kind actor      # force show-level from here
showbible cast add --episode S01E05 "Guest Star"         # force a specific episode
```
