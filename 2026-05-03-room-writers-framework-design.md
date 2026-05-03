---
title: ShowBible — open-source AI writers room framework
status: draft
created: 2026-05-03
authors: [eric]
domain: showbible.com
code: /Users/eric/code/showbible.com
related:
  - "[[ScriptWriter]]"
  - "/Users/eric/code/supernatural-S16"
---

# ShowBible — Open-Source AI Writers Room Framework

> Branded as **showbible.com**. CLI binary: `showbible` (with `bible` as an optional shortcut alias). Throughout this document the working name `room` from earlier drafts has been retired; references to `room <verb>` should be read as `showbible <verb>`. The vault layout, on-disk file names (`pack.yaml`, `people/`, `.room/` runtime directory), and schema fields are unchanged — only the CLI binary and brand are renamed. The runtime directory `.room/` is preserved for now to keep the file-layout decisions decoupled from the brand; if a rename is desired later it's a single migration.

## 1. Overview

ShowBible is an open-source framework for running an AI-driven fan-fiction writers room. The user picks a show (Star Trek, Supernatural, anything), the framework auto-researches the people associated with that show — actors, directors, producers, scriptwriters — and assembles them as agents. Those agents collaborate in a structured production pipeline (pitch → break → draft → polish), occasionally breaking into free-for-all writers-room sessions on contested scenes. The product is a full season of fan-fiction screenplays plus the writers-room transcripts that produced them.

Crucially, agents embody the *actor's* personality, not the character's. Jensen Ackles arguing with Misha Collins about how Dean would react in a scene is the content; the resulting script is a side effect.

### 1.1 Origin & motivation

The author has an existing 20-episode-season project (`supernatural-S16`) built on Paperclip's agent platform. It works, but four problems compound:

1. **Output reads single-voiced.** Sequential review (Jensen pass → Jared pass → …) doesn't produce real disagreement.
2. **Orchestration is brittle.** Long-running runs lose context; agents stall.
3. **No live UX.** Can't sit at the table, watch the room, or steer mid-conversation.
4. **Hardcoded for one show.** Making "Star Trek" requires rewriting most of it.

`room` is a from-scratch rebuild that fixes all four.

### 1.2 Audience

Single-user, run-locally, open-source framework. No SaaS, no auth, no multi-tenancy. Users install the CLI, point it at a vault, and run.

### 1.3 v0.1 scope

A user can:
- Initialize a project and auto-research a show pack
- Edit personalities, lore, and cast
- Run an episode end-to-end with live token streaming
- Intervene at any point as themselves or as any agent
- Accumulate episodes into a season with shared lore and arcs
- Track and cap costs
- Recover cleanly from any crash or interruption

Explicitly deferred to later releases: daemon mode, multi-user, format adapters (storyboards/audio/blog), parallel episode generation, evaluation harness, fine-tuned personality models.

---

## 2. System Architecture

### 2.1 Layers

Three layers, deliberately decoupled:

```
┌──────────────────────────────────────────────────┐
│  Reference Web UI  (Vite + React + SSE client)   │  ← presentation
│  - Live writers-room view                        │
│  - "Tap in" / "Speak as…" controls               │
│  - Show-pack / cast browser                      │
└─────────────────────┬────────────────────────────┘
                      │ Server-Sent Events (events) + REST (commands)
┌─────────────────────┴────────────────────────────┐
│  Engine Process  (single async runtime)          │  ← orchestration
│  ┌────────────────────────────────────────────┐  │
│  │ Director (loop scheduler)                  │  │
│  │  ├─ Phase Machine (pitch/break/draft/…)    │  │
│  │  ├─ Turn Scheduler (whose voice next)      │  │
│  │  └─ Writers-Room Session controller        │  │
│  ├────────────────────────────────────────────┤  │
│  │ Agent Runtime                              │  │
│  │  ├─ Personality loader                     │  │
│  │  ├─ Context builder (RAG over vault)       │  │
│  │  └─ LLM provider adapter                   │  │
│  ├────────────────────────────────────────────┤  │
│  │ Intervention Bus (pause, speak-as, edit)   │  │
│  ├────────────────────────────────────────────┤  │
│  │ Vault Watcher (fsevents/inotify)           │  │
│  │  external-edit detection → auto-pause      │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────┬────────────────────────────┘
                      │ filesystem read/write (atomic, append-only transcripts)
┌─────────────────────┴────────────────────────────┐
│  Vault on disk (markdown + YAML, git-friendly)   │  ← state
│  - Show pack (people, lore, arcs)                │
│  - Episodes (pitches, beats, drafts, scripts)    │
│  - Writers-room transcripts (append-only)        │
│  - .room/ runtime state + indexes (rebuildable)  │
└──────────────────────────────────────────────────┘
```

### 2.2 Key invariants

- **Vault is the source of truth.** Every agent action that produces content is written to disk *before* the next event fires. If the engine dies, `room continue` reconstructs the world from the vault alone.
- **UI is a thin client.** Subscribes to engine events via SSE; sends user actions via REST POST. UI never writes the vault directly.
- **Engine is a single async process.** Agents are coroutines, not subprocesses. Multi-process daemon mode is a designed-for future flag, not v0.1.
- **Loopback only.** Engine binds `127.0.0.1:<random-port>`. No network surface, no auth.
- **Single CLI entry point** (`room`) wraps init, pack management, run, status, fork, export.

### 2.3 Languages

- **Engine:** Python (async, mature LLM ecosystem, rich provider libraries)
- **UI:** TypeScript + Vite + React
- **Distribution:** `pipx install room-writer`. UI ships as static assets bundled inside the Python package, served by the engine on startup. Single install, zero npm.

### 2.4 Out of scope (v0.1)

- Multi-user / shared rooms
- Cloud hosting, deployment, auth
- Daemon mode
- Mobile / Electron
- Multi-vault federation

---

## 3. Data Model

The vault layout is the framework's most-public API. Show packs and personality files get forked, edited, and shared.

### 3.1 Vault layout

```
my-trek-season/
  pack.yaml                          # show + season metadata
  research/                          # raw output of auto-research, kept for provenance
    sources.md
    notes.md
  people/                            # one file per agent
    gene-roddenberry.md
    william-shatner.md
    ...
  lore-bible/
    canon.md                         # established facts, append-only-ish
    glossary.md                      # terms, ships, places
    relationships.md                 # cross-cutting pairwise dynamics (optional summary)
  arcs/
    spock-grief-arc.md               # multi-episode character arcs
  episodes/
    S01E01-the-pilot/
      meta.yaml                      # status, cast present, theme tie-ins
      pitch.md
      beats.md
      writers-room/                  # append-only transcripts per phase/session
        001-phase-pitch.md
        002-phase-break.md
        003-session-act2-fight.md
        004-phase-draft.md
        005-phase-polish.md
      drafts/
        v1-fast.md
        v2-after-room.md
      script.md                      # canonical output
      callbacks.yaml                 # references to other episodes (machine-generated)
  .room/                             # runtime state, gitignore-recommended
    index.sqlite                     # rebuildable embeddings/index
    sessions/                        # paused-room state for resume
    locks/                           # PID-file run lock
```

### 3.2 `pack.yaml`

```yaml
schema: 1
show:
  name: Star Trek
  eras: [TOS, TNG, DS9]
  genre: science fiction
  tone: optimistic, humanist, episodic
season:
  number: 1
  episode_count: 10
  theme: "When the mission outlives the mission statement."
  arc_spine:
    - episode_target: 1
      beat: pilot — establish theme
    - episode_target: 5
      beat: midpoint — theme inverted
    - episode_target: 10
      beat: finale — theme paid off
roles:
  - kind: showrunner
    person: gene-roddenberry
  - kind: director
    person: nicholas-meyer
  - kind: actor
    person: william-shatner
    plays: kirk
  - kind: writer
    person: dorothy-fontana
provider:
  default: anthropic
  fallback: ollama
  per_role:
    lore-keeper: ollama        # cheap calls go local
    showrunner: anthropic      # quality matters here
budget:
  max_dollars_per_episode: 5.00
```

### 3.3 `people/<slug>.md`

Six-layer personality model split into machine-readable frontmatter (layers 1, 3, 4, 6) and human-readable body (layer 5):

```yaml
---
schema: 1
slug: william-shatner
display_name: William Shatner
roles_eligible: [actor]
plays: kirk
voice:
  fingerprint: "halting cadence, dramatic pauses, declarative, leans heroic"
  signature_moves:
    - "fights for Kirk's spotlight"
    - "rewrites lines to be more action-forward"
  sample_lines:
    - "We're not going to let some... bureaucrat tell us how to write Kirk."
beliefs:
  - "Kirk is the moral center; the ship orbits him."
  - "Earned sentiment beats manufactured cleverness."
bio_anchors:
  - "Directed Star Trek V, knows the chair from both sides."
  - "Has publicly clashed with Nimoy over screen time."
trait_axes:
  openness: 0.4
  conscientiousness: 0.6
  extraversion: 0.9
  agreeableness: 0.5
  neuroticism: 0.6
---

# William Shatner — relationships

## With Leonard Nimoy
Decades of friction made into friendship. Public spats about screen time
became affectionate ribbing in late life. In the room: argues for Kirk
moments, then often backs Nimoy's quieter takes once they're on the page.

## With Nicholas Meyer
Director who finally gave Kirk gravity (Wrath of Khan). Shatner trusts him.
Will defer to Meyer on tone where he wouldn't to other directors.
```

**Layered ingredients:**

| Layer | Source | Required? | Where |
|---|---|---|---|
| 1. Voice fingerprint | Auto-research, hand-tunable | Required | `voice:` |
| 2. Verbatim source quotes (RAG) | Auto-research (interview corpora) | Optional, power-user | Future: `quotes/` directory |
| 3. Trait axes (Big 5 etc.) | Auto-research, inferred | Optional | `trait_axes:` |
| 4. Beliefs & preferences | Auto-research, hand-tuned | Required | `beliefs:` |
| 5. Relationship matrix | Auto-research, hand-tuned | Strongly recommended | Markdown body |
| 6. Bio anchors | Auto-research | Required | `bio_anchors:` |

**Relationships are stored per-person, not centrally.** Each person's file is self-contained. Two perspectives on the same relationship is realistic, not redundant — Shatner's view of Nimoy is not the same fact as Nimoy's view of Shatner.

### 3.4 `lore-bible/canon.md`

Append-only-with-edits. The Lore Keeper agent owns this file:

```markdown
## Facts

- **Klingon-Federation cease-fire in S01E03** — Established in writers-room
  for S01E03 (act 3 negotiation scene). Ratified by Roddenberry. Spock present.
  *Sources: episodes/S01E03/script.md L342-L389*

- **Kirk has an estranged son** — Hinted in S01E05 cold open, confirmed in
  S01E07 pitch. *Sources: episodes/S01E07/pitch.md*
```

### 3.5 `arcs/<slug>.md`

```yaml
---
schema: 1
character: spock
season: 1
beats:
  - episode_target: 2
    beat: "denies grief intellectually"
    status: planned
  - episode_target: 5
    beat: "grief breaks through during Vulcan ritual"
    status: planned
  - episode_target: 8
    beat: "accepts grief, integrates it"
    status: planned
---

# Spock's grief arc
Following the death of Sarek in S01E01 cold open...
```

### 3.6 Writers-room transcripts

Append-only chat log, one file per phase or session. User interventions are first-class entries with `author=user, voicing=<agent-slug>` provenance — every line, forever, is auditable as AI- or human-authored.

```markdown
---
phase: break
started: 2026-05-03T14:22:11Z
participants: [gene-roddenberry, nicholas-meyer, dorothy-fontana, william-shatner]
---

## Roddenberry (Showrunner) — 14:22:14
Cold open: Sarek dies. Spock gets the news...

## Shatner (as Kirk) — 14:22:31
I'd rewrite act 1's bridge dialogue...

## user (Director seat, intervention) — 14:22:45
Less Kirk-knows-everything. Lean into him being out of the loop.

## Shatner (as Kirk) — 14:22:51
Fine. He's frustrated, suspects something...
```

**Heading format (uniform across all entries):** `## <author> (<role>[, intervention]) — <HH:MM:SS>`. Parsers can split on ` — ` for the timestamp and parse the parenthesized role; the optional `, intervention` suffix marks user contributions. Per-line metadata (provenance, voicing target, scope) is stored alongside in `meta.yaml` keyed by timestamp, not in the heading.

### 3.7 Schema versioning

Every YAML/frontmatter file carries `schema: <int>`. Engine refuses to load future-version files (forward compat); auto-migrates past-version files (backward compat).

A migration is **destructive** if it removes fields, renames fields without an alias, or rewrites prose in markdown bodies. Non-destructive migrations (adding new optional fields, populating defaults) run silently and log to `.room/migrations.log`.

Destructive migrations:
- **Interactive contexts** (TTY attached): show a unified diff of proposed changes per file and require explicit "y" confirmation; "n" aborts the engine startup.
- **Non-interactive contexts** (`--keep-going`, CI, `--json`): refuse to run; engine exits with a clear message instructing the user to run `room migrate` interactively first. `room migrate --yes` exists for users who explicitly accept the risk.

A backup of every modified file is written to `.room/migrations/<timestamp>/` before any destructive write. v0.1 ships schema 1 for all file types.

### 3.8 Show pack distribution

Show packs are git repos. Sharing = `git push`. Installing a community pack: `room pack add star-trek --from <git-url>`. The framework treats community packs as input data, not extensions — no code execution, only YAML/markdown parsing.

---

## 4. Orchestration

### 4.1 The phase machine

```
[ pitch ] → [ break ] → [ fast-draft ] → [ room-pass ] → [ polish ] → [ continuity-check ] → DONE
       │          │            │              │              │                │
       └──────────┴────────────┴──────────────┴──────────────┴────────────────┘
                                          │
                            any phase may spawn ad-hoc
                            [ session ] when triggered by:
                              - actor flag (room-pass)
                              - Director-identified contention
                              - explicit user request
```

| Phase | Goal | Lead agent | Default exit condition |
|---|---|---|---|
| pitch | One-paragraph episode concept tied to season theme + arcs | Showrunner | Showrunner `commit_pitch` event |
| break | Pitch → act structure + scene list | Director | Director `commit_beats` event |
| fast-draft | First-pass dialogue for each scene | Writers (round-robin) | All scenes have a draft |
| room-pass | Each actor reviews their character's lines; flags weak scenes | Actors (parallel) | Each actor `pass` or `flag` |
| polish | Director integrates flags + rewrites into clean draft | Director | Director `commit_draft` event |
| continuity-check | Lore Keeper validates against canon + arcs | Lore Keeper | `clean` or `flagged_unresolved` |

Phase transitions are first-class events written to `episodes/<id>/meta.yaml` with timestamps.

### 4.2 The turn scheduler

Within a phase, agents take turns according to a phase-specific scheduler:

- **Single-speaker phases** (pitch, break, polish): the lead agent runs; others read but don't write.
- **Round-robin phases** (fast-draft): writers cycle through scenes assigned to them.
- **Parallel phases** (room-pass): all actors generate concurrently with no shared state during the pass; results merged after.
- **Free-for-all phases** (sessions): bid-based selector — see 4.3.

Scheduler emits `agent.turn_started`, `agent.token`, `agent.turn_ended` events; tokens stream live.

### 4.3 Writers-Room Sessions

A **Session** is an ad-hoc free-for-all triggered by:

1. An actor flagging a scene as "wrong for my character" during room-pass
2. The Director identifying a contested beat
3. The user explicitly calling one ("session on the act 2 climax")

**Session bounds:**
- **Cap:** max N turns (default 12, configurable in `pack.yaml`)
- **Timer:** max wall-clock minutes (default 5)
- **Director's call:** Director can end early if consensus or repetition

**Bid-based speaker selector:**

1. After each turn, all eligible agents simultaneously emit a "bid" — a small structured number 0–1 representing how much they have to add. Bids are cheap (single-token-ish output, ideally on a small/local model).
2. Highest bidder speaks next.
3. **Tie-break order:** (a) least-recently-spoken in this session, (b) randomized stable seed (deterministic per session for replayability).
4. The Director gets a small bonus to bid weight, so they can step in to refocus.

(A future schema could add an explicit `relationship_weights:` numeric field to personality files for richer dynamics, but v0.1 keeps relationships as free-text prose only — they inform the *content* of bids via context-injection, not the selector arithmetic.)

This produces the *feel* of free-for-all without round-robin or single-agent dominance.

**Risk note:** the bid-based selector is the highest-uncertainty subsystem. Fallback: if empirical results show degenerate behavior, switch to Director-called turns within sessions (predictable, less emergent). Worth A/B during early development.

Sessions get their own transcript file `writers-room/NNN-session-<topic>.md`. The session's resolution (an integrated change) is written by the Director and feeds back to the calling phase.

### 4.4 Parallel vs. serial

- **Within a phase:** serial by default, tokens stream live. Parallel only in `room-pass` because actors review independently.
- **Across episodes:** serial in v0.1. Parallel/background episode generation is a v1.x feature.

### 4.5 Season-level scheduling

- **Default (v0.1):** `room run --episode <id>`. User picks the next episode; Showrunner picks pitch within it. Maps to the gamification frame.
- **Power-user (v0.1, thin wrapper):** `room run --season` runs episodes in order using the `arc_spine`, with full intervention available.
- **Auto-pitch:** Showrunner consults `arc_spine` and `arcs/` to draft each pitch; user always has a chance to intervene.

---

## 5. User Intervention

### 5.1 Three intervention modes

| Mode | What it does | When |
|---|---|---|
| **Note** | Drops a steering note the next agent reads as production guidance ("less Cas in act 2") | Drift correction, gentle nudges |
| **Speak as self** | Adds a peer voice to the transcript with user's name + chosen role (Director, Producer, Guest Writer) | User wants to be at the table as themselves |
| **Speak as agent** | User puppets an existing agent for one turn / scene / until released | User disagrees with how that agent is voicing their character |

All three appear as first-class transcript entries with provenance preserved forever.

### 5.2 The intervention bus

- User actions: `POST /intervene` with `{type, scope, content}`
- Engine has a per-room intervention queue; Director drains it at every turn boundary.
- **Queue ordering:** strict FIFO by submission timestamp. Multiple interventions queued before the next turn boundary all apply, in arrival order. Notes are added to context first, then `speak as self` entries are written to the transcript, then `speak as agent` puppet flags are evaluated when that agent's turn arrives.
- **Default:** queued interventions apply at the next turn boundary, not mid-token.
- **Hard pause** (Ctrl+P / pause button): freezes engine immediately, even mid-token. UI shows "paused, room awaiting you."

### 5.3 Speak-as-agent: puppeting

1. Engine sets a flag on the agent's scheduled turn: `puppeted_by=user`.
2. When the agent's turn arrives, engine emits `agent.turn_started` with `puppeted=true` and opens a text input prefilled with "as <agent>…".
3. User types the line. On submit, written to transcript with `author=user, voicing=<agent-slug>`.
4. Other agents read it as that agent's contribution for downstream context.
5. Scope releases at: (a) one turn for `--turn`, (b) scene/phase end for `--scene`/`--phase`, (c) explicit release for `--until-released`.

### 5.4 Drift detection

Per the user's "intervene when things drift" criterion: the engine watches for drift and surfaces it as soft, non-blocking alerts.

| Signal | Mechanism | Threshold |
|---|---|---|
| **Theme drift** | After each phase, Showrunner rates "how on-theme, 1–5?" against season theme | <3 raises yellow flag |
| **Voice drift** | Per-actor check: does this dialogue sound like this actor would write it? | <3 raises yellow flag |
| **Loop drift** | Scheduler watches for repetition in sessions (same agent same point twice) | After 2nd repetition, "going in circles" badge (deterministic, no LLM call) |

Alerts are non-blocking. UI shows a small icon; click to see what tripped the signal. Room keeps running.

**Cost note:** theme- and voice-drift checks each add one LLM call per phase per signal. They route through the `drift-detector` role in `provider.per_role`, defaulting to a small/local model (Ollama). Loop drift is purely structural, no LLM. Drift checks are skippable via `pack.yaml` (`drift.enabled: false`) for cost-sensitive runs.

### 5.5 UI shape

```
┌─────────────────────────────────────────────────────────────────┐
│ Header: project · episode · phase · ⏸ pause · ⚠ 1 drift signal  │
├──────────────┬──────────────────────────────────────┬───────────┤
│  Cast        │  Transcript (live, tokens stream)    │  Context  │
│  - Roddenb.  │                                      │           │
│  - Meyer     │  ## Roddenberry — 14:22:14           │  Pitch:   │
│  - Shatner   │  OK so the pilot establishes...      │  ...      │
│  - Nimoy     │                                      │  Beats:   │
│  - Fontana   │  ## Meyer — 14:22:32                 │  ...      │
│              │  I'd open cold on Sarek's death...   │           │
│  click to    │                                      │  Arcs     │
│  speak as ▼  │  ## Shatner (as Kirk) — 14:23:08     │  active:  │
│              │  [streaming...] ▌                    │  - Spock  │
│              │                                      │    grief  │
│              ├──────────────────────────────────────┤           │
│              │ [💬 Note] [🎭 Speak as ▼] [⏸ Pause] │           │
└──────────────┴──────────────────────────────────────┴───────────┘
```

The right sidebar showing what the room is currently consulting (pitch, beats, active arcs, lore facts) is a deliberate "show your work" investment — it builds user trust by making the AI's context visible.

### 5.6 Leave & return

- **Default:** closing browser or Ctrl+C **pauses** the room. State on disk. `room continue` resumes.
- **`--keep-going`:** engine continues without UI. `room status` shows progress; `room attach` reopens browser.
- Vault is always fully consistent on disk; user can browse paused-state in Obsidian without confusing the engine.

---

## 6. LLM Provider Abstraction

### 6.1 Adapter interface

Thin, intentionally minimal:

```python
class Provider(Protocol):
    async def stream(
        self,
        system: str,
        messages: list[Message],
        tools: list[Tool] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.8,
    ) -> AsyncIterator[StreamEvent]:
        ...

    def count_tokens(
        self,
        system: str,
        messages: list[Message],
        tools: list[Tool] | None = None,
    ) -> int:
        """Pre-flight token count for budget checks and compaction decisions.
        Implementations may use the provider's tokenizer endpoint or a local
        approximation (tiktoken, etc.). Must not require a network round-trip
        to be acceptably fast for use in §8.2 layered context construction."""
        ...
```

`StreamEvent` ∈ {`TokenDelta`, `ToolCall`, `Done(stop_reason, usage)`}.

### 6.2 Bundled adapters (v0.1)

- `anthropic` — Claude (default)
- `openai` — GPT family
- `ollama` — local models
- `mock` — deterministic, for tests

### 6.3 Configuration cascade

Highest precedence wins:

1. Per-turn override (`--override-provider=ollama`)
2. Per-agent role in `pack.yaml` (`provider.per_role`)
3. Project default in `pack.yaml`
4. User default in `~/.room/config.yaml`
5. Built-in default: Anthropic if `ANTHROPIC_API_KEY` set, else Ollama if reachable, else error with clear instructions

**Per-role routing matters for cost.** Cheap "bid" calls go to Ollama; "draft a scene" calls go to Claude. Built into the config schema from day one.

### 6.4 Out of scope (v0.1)

- Hand-tuned prompt cache layouts (we use Anthropic's caching when available, no exotic strategies)
- Fine-tuned personality models
- Embeddings beyond the simple SQLite index

---

## 7. CLI Surface

```
room                                    # status of cwd project (or help)

# Project lifecycle
room init <name>                        # scaffold empty project
room init <name> --from <show-name>     # init + auto-research show pack
room status                             # episode, phase, drift signals

# Show pack management
room pack add <show>                    # auto-research a show
room pack add <show> --from <git-url>   # install community pack
room pack edit <person-slug>            # open person's md in $EDITOR
room pack export                        # bundle pack as shareable git repo
room pack list                          # show installed packs

# Casting
room cast                               # interactive: pick people, assign roles
room cast --auto                        # Showrunner picks default cast

# Running
room run                                # next pending episode (or attach to current)
room run --episode <id>                 # specific episode
room run --season                       # all remaining episodes in order
room run --keep-going                   # don't pause when UI closes
room pause / room resume / room continue
room attach                             # open browser to running room

# Episode lifecycle
room episode new                        # interactive: pitch + slot a new episode
room episode list
room episode fork <id>                  # branch a variant from existing episode

# Inspection / debug
room transcript <ep-id>
room lore                               # print canon.md
room arcs                               # arc status
room cost                               # token + dollar usage
room doctor                             # diagnose config, providers, vault integrity
```

**Design principles:**
- Verbs are noun + action (`room pack add`, `room episode new`) — git/wrangler/supabase shape
- `room` with no args = `room status` in a project, `room help` outside one
- Every command produces a single visible side effect in the vault
- Safe defaults; explicit power flags
- `--json` flag on every read-side command for scripting
- `room doctor` is a deliberate investment to reduce support burden

**Exit codes (uniform across the CLI):**

| Code | Meaning |
|---|---|
| `0` | Success / clean |
| `1` | Generic failure |
| `2` | Usage error (bad flags / args) |
| `3` | Vault not found / wrong working directory |
| `4` | Vault integrity issue (`room doctor` reports problems) |
| `5` | Provider configuration error (no key, no fallback reachable) |
| `6` | Budget cap reached (per `pack.yaml` budget block) |
| `7` | Schema migration required (run `room migrate`) |
| `130` | User-interrupted (Ctrl+C, standard Unix convention) |

---

## 8. Failure Handling & Recovery

### 8.1 Failure taxonomy

| Failure | Frequency | Recovery |
|---|---|---|
| Provider timeout / 5xx | Common | Exponential backoff (3 attempts), then fail turn |
| Provider rate limit | Common | Backoff per `retry-after`; UI shows "waiting on rate limit" |
| Token budget exceeded | Common at season scale | Context compaction (§8.2) |
| Invalid structured output | Occasional | Re-prompt once with explicit schema correction, then fail turn |
| Engine crash / OS kill | Rare | Vault is truth → `room continue` rebuilds |
| User edits files mid-run | Possible | Vault watcher pauses room, surfaces "vault changed — review and resume?" |
| Lore contradiction | Common output-quality | Lore Keeper flags, doesn't block; user decides |
| SSE connection drop | Common | UI auto-reconnects; engine buffers stream 5s |
| Infinite session loop | Possible | Hard turn cap + drift detector breaks repetition |

### 8.2 Context compaction

A 10-episode season's full transcript will not fit any context window. The Context Builder constructs each turn's prompt from layered sources:

1. **System prompt** (small, static): role description, personality file frontmatter
2. **Show context** (medium, cached): `pack.yaml` + season theme + arc spine
3. **Episode context** (medium): current episode's pitch + beats + recent transcript
4. **Selective long-term context** (small, retrieved): top-K relevant facts from `lore-bible/canon.md` + arcs, retrieved by embedding query against current beat
5. **Relationship context** (small, conditional): if another specific agent is active in this turn, load that pairwise relationship section
6. **Recent transcript window** (large): last K turns of current phase/session, full text

Target: stay under 30K tokens per turn for v0.1. Layers 1–3 are cacheable (Anthropic prompt cache hits = cheap). Layer 4 is the magic — agents reference earlier episodes because the most-relevant facts are pulled in, not because they have full transcripts.

The SQLite index (`.room/index.sqlite`) holds embeddings for every paragraph in the vault — lore facts, prior beats, prior dialogue, personality sections. Rebuildable from markdown.

### 8.3 Vault integrity

- **Atomic writes:** write to `*.tmp`, fsync, rename. Markdown files never half-written.
- **Schema versioning:** future-version files refused; past-version files auto-migrated per §3.7.
- **Vault lock:** `.room/locks/run.lock` PID-file prevents concurrent engines. `room doctor` cleans stale locks.
- **Vault Watcher:** when the engine is running, a filesystem watcher (fsevents on macOS, inotify on Linux, polling fallback for unsupported platforms) monitors the vault for **external** edits — i.e., writes that did not originate from the engine itself. The watcher distinguishes engine writes from external edits via an in-memory write log (`(path, mtime, hash)` for every engine write). When an external edit is detected, the engine soft-pauses the current turn at the next boundary, surfaces "vault changed externally — review and resume?" in the UI, and exposes the changed files. User chooses to (a) reload (re-read the file, continue), (b) revert (overwrite from last engine write), or (c) abort the run.
- **`room doctor`** validates: schema versions, broken cross-file references, orphaned files, missing personality files for cast members, provider config, index freshness, stale locks.

### 8.4 Cost guardrails

- **Live cost ticker** in UI header: tokens used, $ estimate, by-provider breakdown
- **`pack.yaml` budget block:** `max_dollars_per_episode: 5.00`. Confirmation at 80%, hard stop at 100%.
- **`room cost`:** cumulative spend per episode/agent/provider
- **Mock provider:** end-to-end tests run for free

---

## 9. Testing Strategy

Three layers, matching the cost/determinism gradient:

### 9.1 Unit tests (deterministic, fast)

Everything that isn't an LLM call:
- Phase machine state transitions
- Turn scheduler (with `mock` provider)
- Context Builder (given vault state → expected prompt)
- Vault read/write atomicity
- Schema migration
- Intervention queue ordering and provenance writing

### 9.2 Integration tests (mock provider, full pipeline)

Using `mock` provider with scripted responses:
- Full mini-episode end-to-end with mock agents
- Vault state correctness after each phase
- Intervention flow (note → speak as self → speak as agent) produces correct provenance
- Failure recovery: kill engine mid-phase → `room continue` produces same final state

### 9.3 Smoke tests (real provider, gated)

Opt-in (`pytest -m smoke`) using a cheap real model:
- Generate a 3-line scene with 2 agents (verify *something* coherent)
- Run a 5-turn session (verify bid scheduler doesn't loop or starve)
- Apply a user note mid-phase (verify next agent reads it)

### 9.4 What we deliberately do NOT test

Output quality. "Is the script good?" is evaluation, not testing. Plumbing correctness is the framework's testing job; quality is judged by humans against actual fan-fiction output.

### 9.5 Evaluation harness (post-v0.1)

`room eval` command — takes a known scenario, runs it, asks a judge model (or user) to score voice fidelity, drama quality, theme alignment. Drives quality regression tracking. Designed-for in v0.1, delivered later.

---

## 10. v0.1 Scope Summary

**Ships:**
- Single-vault season runner: pick a show, run episodes, season state accumulates
- Hybrid show packs (auto-research → editable → shareable as git repos)
- Six-layer personality model (frontmatter + relationship markdown body)
- Phase machine + bid-based session scheduler
- Live observer UI with note / speak-as-self / speak-as-agent intervention
- Drift detection (theme, voice, loop) as soft alerts
- Provider abstraction with anthropic / openai / ollama / mock + per-role routing
- Markdown-first vault, git-friendly, Obsidian-native
- CLI: init, pack, cast, run, status, attach, transcript, lore, arcs, cost, doctor
- Cost guardrails + budget caps
- Three-tier testing strategy

**Deferred (v1.x+):**
- Daemon mode (designed-for, not delivered)
- Multi-user / shared rooms / auth
- Format adapters (storyboards, audio, blog) — pluggable hook surface only
- Background/parallel episode generation
- `room eval` evaluation harness
- Fine-tuned personality models
- Verbatim-quotes RAG (personality layer 2)

---

## 11. Open Risks & Decisions

| Risk | Mitigation |
|---|---|
| Bid-based session scheduler degenerates (loops, starvation, dominance) | A/B against Director-called fallback; hard turn caps; loop detector |
| Auto-research produces low-quality personality drafts | Always human-editable; `room pack edit` is one keystroke; community packs improve over time |
| Long-context costs balloon for season runs | Aggressive layered compaction; per-role provider routing; budget caps |
| OSS sustainability (who maintains?) | Out of scope for this design; framework is built so it can outlast its author by being simple and config-driven |
| "Personality of actor not character" is hard to research | Auto-research draws on interviews, panels, podcasts; user always has final edit; degraded gracefully if data is thin |
| Token streaming UX feels janky | Engine-side buffering on SSE drops; UI graceful re-attach; mid-token pause is rare-but-supported via hard pause |

---

## 12. Naming

**Brand:** ShowBible (domain: `showbible.com`, owned).

**CLI binary:** `showbible`. Optional shortcut alias `bible` provided for terseness (`bible run`, `bible cast`). The `showbible` form is canonical in docs, scripts, and error messages.

**Python package (PyPI):** `showbible` (install: `pipx install showbible`).

**npm package (UI):** internal only — UI ships bundled inside the Python package per §2.3, no separate npm publish.

**Code repository:** `/Users/eric/code/showbible.com`. GitHub: TBD (likely `github.com/<owner>/showbible` once an org is chosen; the `.com` directory suffix is local-only convention to mirror the domain).

**Vault internal directory:** `.room/` retained for v0.1 to decouple brand decisions from on-disk schema. A future rename to `.showbible/` is one migration if desired.

---

## 13. Glossary

- **Vault** — the on-disk project directory; markdown source of truth.
- **Show pack** — `pack.yaml` + `people/` + `lore-bible/` + `arcs/`. The reusable, shareable unit.
- **Cast** — the subset of pack `people` activated as agents for this season's room.
- **Phase** — a node in the per-episode state machine (pitch / break / draft / room-pass / polish / continuity-check).
- **Session** — an ad-hoc free-for-all writers-room moment within a phase, bounded by turn cap and timer.
- **Intervention** — any user contribution to the room (note, speak as self, speak as agent).
- **Provenance** — per-line attribution in transcripts: AI-generated by which agent, or human-authored by user voicing which agent.
- **Drift** — soft signals that output is straying from theme, voice, or productive discussion.
