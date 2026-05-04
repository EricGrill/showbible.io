# Textual TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the curses dashboard with a Textual app that keeps the user navigating freely while episode runs and AI suggestions happen in the background, refreshes vault state every ~1s, and brings Arc and Lore to feature parity with Cast.

**Architecture:** Single Textual app (`ShowBibleApp`) booted from `cmd_tui`. Long calls dispatch through Textual's `@work(thread=True)` so the existing sync `engine.run_episode` and provider stack stay unchanged. A 1s `set_interval` calls `AppState.refresh_from_disk()`; reactive watchers on the App propagate changes to panes. Modals (`AddCastScreen`, `AddArcBeatScreen`, `AddLoreScreen`, `AISuggestScreen`, `ConfirmScreen`, `SnapshotScreen`, `DoctorScreen`) are pushed/popped via the standard Textual `push_screen` flow.

**Tech Stack:** Python 3.11+, Textual ≥ 0.86 (pulls Rich), pytest + pytest-asyncio. No other new dependencies.

**Spec:** [2026-05-03-textual-tui-design.md](2026-05-03-textual-tui-design.md)

---

## File Structure

Files created or modified by this plan:

```
showbible/
  cli.py                                  # MODIFY: gut curses helpers, refactor cmd_arcs_add/cmd_lore_add, add suggest commands, swap cmd_tui body
  vault.py                                # MODIFY: add lore_facts/LoreFact + arc/lore mutators
  tui/                                    # CREATE
    __init__.py
    app.py                                # CREATE: ShowBibleApp(App), top-level CSS, bindings
    state.py                              # CREATE: AppState, refresh_from_disk
    runs.py                               # CREATE: RunHandle, RunRegistry, progress bridge
    panes/
      __init__.py
      base.py                             # CREATE: BasePane (Horizontal list+detail shell)
      episodes.py                         # CREATE: EpisodesPane
      cast.py                             # CREATE: CastPane
      arc.py                              # CREATE: ArcPane
      lore.py                             # CREATE: LorePane
      outputs.py                          # CREATE: OutputsPane (Rich preview + $EDITOR)
      run_detail.py                       # CREATE: RunDetailPane
    screens/
      __init__.py
      add_cast.py                         # CREATE: AddCastScreen ModalScreen
      add_arc_beat.py                     # CREATE: AddArcBeatScreen ModalScreen
      add_lore.py                         # CREATE: AddLoreScreen ModalScreen
      ai_suggest.py                       # CREATE: AISuggestScreen ModalScreen
      confirm.py                          # CREATE: ConfirmScreen ModalScreen
      snapshot.py                         # CREATE: SnapshotScreen ModalScreen
      doctor.py                           # CREATE: DoctorScreen ModalScreen
    widgets/
      __init__.py
      sidebar.py                          # CREATE: Sidebar widget
      run_status.py                       # CREATE: RunStatus footer toast
      entity_form.py                      # CREATE: EntityForm reusable form layout
pyproject.toml                            # MODIFY: add textual + pytest-asyncio
tests/
  test_showbible.py                       # MODIFY: add helper + suggest unit tests + state tests
  test_tui_smoke.py                       # CREATE: 5 Pilot smoke tests
```

---

## Stage 1 — Framework-neutral foundation

Vault helpers and CLI suggest commands the Textual panes need. Each task is fully self-contained.

### Task 1: Add `textual` and `pytest-asyncio` dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read the current `[project]` block**

```bash
grep -n "dependencies\|dependency-groups\|^\[project" /Users/eric/code/showbible.io/pyproject.toml
```

Expected output: a `[project]` block with `dependencies = []`, and (after Task 0 of the prior plan landed) a `[dependency-groups]` table with `dev = ["pytest>=9.0.3"]`.

- [ ] **Step 2: Add `textual` to `[project] dependencies`**

Edit `pyproject.toml`. Replace:

```toml
dependencies = []
```

with:

```toml
dependencies = ["textual>=0.86"]
```

- [ ] **Step 3: Add `pytest-asyncio` to dev dependencies**

In the `[dependency-groups]` block, replace:

```toml
dev = ["pytest>=9.0.3"]
```

with:

```toml
dev = ["pytest>=9.0.3", "pytest-asyncio>=0.24"]
```

- [ ] **Step 4: Add the asyncio mode setting under `[tool.pytest.ini_options]`**

Find the existing `[tool.pytest.ini_options]` block (it should already contain `testpaths = ["tests"]`) and add `asyncio_mode = "auto"` so async tests don't need an explicit marker:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 5: Sync the lockfile and confirm both packages install**

```bash
cd /Users/eric/code/showbible.io
uv sync
```

Expected: `uv` resolves and installs `textual` (>=0.86) and `pytest-asyncio` (>=0.24) without errors. The `uv.lock` will be updated.

- [ ] **Step 6: Verify imports work**

```bash
python -c "import textual; import pytest_asyncio; print(textual.__version__)"
```

Expected: prints a version string ≥ 0.86 and exits 0.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add textual and pytest-asyncio dependencies"
```

---

### Task 2: `add_arc_beat` / `update_arc_beat` / `remove_arc_beat`

**Files:**
- Modify: `showbible/vault.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_showbible.py`:

```python
def test_arc_beat_round_trip(tmp_path: Path) -> None:
    from showbible.vault import add_arc_beat, arc_beats, remove_arc_beat, update_arc_beat

    vault = init_vault(tmp_path / "demo")

    add_arc_beat(vault, "season-theme", "S01E01", "planned", "open the season")
    add_arc_beat(vault, "season-theme", "S01E02", "planned", "turn the screw")
    add_arc_beat(vault, "ensemble", "S01E01", "planned", "introduce the rival")

    summary = [(b.arc, b.episode, b.status, b.beat) for b in arc_beats(vault)]
    assert ("season-theme", "S01E01", "planned", "open the season") in summary
    assert ("season-theme", "S01E02", "planned", "turn the screw") in summary
    assert ("ensemble", "S01E01", "planned", "introduce the rival") in summary

    update_arc_beat(
        vault,
        arc_slug="season-theme",
        episode_id="S01E02",
        original_beat="turn the screw",
        new_episode_id="S01E03",
        new_status="in-progress",
        new_beat="finally turn the screw",
    )
    after_update = [(b.arc, b.episode, b.status, b.beat) for b in arc_beats(vault)]
    assert ("season-theme", "S01E03", "in-progress", "finally turn the screw") in after_update
    assert ("season-theme", "S01E02", "planned", "turn the screw") not in after_update

    remove_arc_beat(vault, "ensemble", "S01E01", "introduce the rival")
    after_remove = [(b.arc, b.episode) for b in arc_beats(vault)]
    assert ("ensemble", "S01E01") not in after_remove

    season = (vault / "arcs" / "season-theme.md").read_text(encoding="utf-8")
    assert season.startswith("# Season Theme")
    assert "## Episode Beats" in season
```

- [ ] **Step 2: Run the test, expect ImportError**

```bash
python -m pytest tests/test_showbible.py::test_arc_beat_round_trip -v
```

Expected: `ImportError: cannot import name 'add_arc_beat' from 'showbible.vault'`.

- [ ] **Step 3: Implement the helpers in `showbible/vault.py`**

Add to `vault.py` (place near `arc_beats` from commit `5101ad2`):

```python
def _arc_file(vault: Path, arc_slug: str) -> Path:
    return vault / "arcs" / f"{slugify(arc_slug)}.md"


def _arc_line(episode_id: str, status: str, beat: str) -> str:
    return f"- {episode_id.upper()} [{status.strip()}] {beat.strip()}"


def add_arc_beat(vault: Path, arc_slug: str, episode_id: str, status: str, beat: str) -> Path:
    path = _arc_file(vault, arc_slug)
    if not path.exists():
        title = arc_slug.replace("-", " ").title()
        atomic_write_text(path, f"# {title}\n\n")
    body = path.read_text(encoding="utf-8").rstrip()
    if "## Episode Beats" not in body:
        body += "\n\n## Episode Beats\n"
    body = body.rstrip() + "\n" + _arc_line(episode_id, status, beat) + "\n"
    atomic_write_text(path, body)
    return path


def update_arc_beat(
    vault: Path,
    *,
    arc_slug: str,
    episode_id: str,
    original_beat: str,
    new_episode_id: str,
    new_status: str,
    new_beat: str,
) -> Path:
    path = _arc_file(vault, arc_slug)
    if not path.exists():
        raise VaultError(f"arc not found: {arc_slug}")
    text = path.read_text(encoding="utf-8")
    new_text, count = _replace_arc_line(text, episode_id, original_beat, _arc_line(new_episode_id, new_status, new_beat))
    if count == 0:
        raise VaultError(f"arc beat not found in {arc_slug}: {episode_id} {original_beat!r}")
    atomic_write_text(path, new_text)
    return path


def remove_arc_beat(vault: Path, arc_slug: str, episode_id: str, beat: str) -> Path:
    path = _arc_file(vault, arc_slug)
    if not path.exists():
        raise VaultError(f"arc not found: {arc_slug}")
    text = path.read_text(encoding="utf-8")
    new_text, count = _replace_arc_line(text, episode_id, beat, replacement=None)
    if count == 0:
        raise VaultError(f"arc beat not found in {arc_slug}: {episode_id} {beat!r}")
    atomic_write_text(path, new_text)
    return path


def _replace_arc_line(
    text: str,
    episode_id: str,
    beat: str,
    replacement: str | None,
) -> tuple[str, int]:
    pattern = re.compile(
        rf"^-\s*{re.escape(episode_id.upper())}\s+\[[^\]]+\]\s+{re.escape(beat.strip())}\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if replacement is None:
        new_text, count = pattern.subn("", text)
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        return new_text, count
    return pattern.subn(replacement, text)
```

- [ ] **Step 4: Run the test, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_arc_beat_round_trip -v
```

- [ ] **Step 5: Run the full suite to confirm no regressions**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add showbible/vault.py tests/test_showbible.py
git commit -m "feat(vault): add/update/remove_arc_beat helpers"
```

---

### Task 3: Refactor `cmd_arcs_add` to use the helper

**Files:**
- Modify: `showbible/cli.py:584-597`

- [ ] **Step 1: Confirm the existing CLI test passes pre-refactor**

```bash
python -m pytest tests/test_showbible.py::test_arcs_follow_current_episode_folder -v
```

Expected: PASS (baseline).

- [ ] **Step 2: Replace the body of `cmd_arcs_add`**

Edit `showbible/cli.py:584-597`. Replace the function with:

```python
def cmd_arcs_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _arc_episode_scope(vault, args) or "S01E01"
    path = add_arc_beat(vault, args.arc, episode_id, args.status, args.beat)
    print(f"Added arc beat to {path.name}: {episode_id} [{args.status}] {args.beat.strip()}")
    return 0
```

Ensure `add_arc_beat` is imported. Find the existing `from showbible.vault import …` block in `cli.py` and add `add_arc_beat` to the imported names if missing.

- [ ] **Step 3: Run the same CLI test, expect identical output**

```bash
python -m pytest tests/test_showbible.py::test_arcs_follow_current_episode_folder -v
```

Expected: PASS — output text and on-disk format are byte-identical.

- [ ] **Step 4: Run the full suite**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add showbible/cli.py
git commit -m "refactor(cli): cmd_arcs_add uses add_arc_beat helper"
```

---

### Task 4: `lore_facts(vault)` reader

The on-disk format written by `cmd_lore_add` is:

```
- **Manual fact** - <fact text> *Source: <source>*
```

`lore_facts` parses this back into structured records, tolerating bullets without the `**Manual fact**` prefix or the `*Source: …*` suffix.

**Files:**
- Modify: `showbible/vault.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_showbible.py`:

```python
def test_lore_facts_parses_canon(tmp_path: Path) -> None:
    from showbible.vault import lore_facts

    vault = init_vault(tmp_path / "demo")
    atomic_write_text(
        vault / "lore-bible" / "canon.md",
        "# Canon\n\n"
        "## Facts\n\n"
        "- **Manual fact** - The protocol is older than the colony. *Source: S01E02*\n"
        "- **Manual fact** - The bell only rings on the equinox. *Source: manual*\n"
        "- A bare bullet survives untouched.\n",
    )

    facts = lore_facts(vault)

    assert [(f.text, f.source) for f in facts] == [
        ("The protocol is older than the colony.", "S01E02"),
        ("The bell only rings on the equinox.", "manual"),
        ("A bare bullet survives untouched.", "manual"),
    ]
    assert facts[0].file == vault / "lore-bible" / "canon.md"
```

- [ ] **Step 2: Run, expect ImportError**

```bash
python -m pytest tests/test_showbible.py::test_lore_facts_parses_canon -v
```

- [ ] **Step 3: Implement in `showbible/vault.py`**

Add the dataclass near `ArcBeat`:

```python
@dataclass(frozen=True)
class LoreFact:
    text: str
    source: str
    file: Path
```

Add the parser:

```python
_LORE_FACT_RE = re.compile(
    r"^-\s*(?:\*\*Manual fact\*\*\s*-\s*)?(.+?)(?:\s*\*Source:\s*([^*]+?)\s*\*)?\s*$"
)


def lore_facts(vault: Path) -> list[LoreFact]:
    canon = vault / "lore-bible" / "canon.md"
    if not canon.exists():
        return []
    in_facts = False
    results: list[LoreFact] = []
    for raw in canon.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if stripped.startswith("## "):
            in_facts = stripped.lower().startswith("## facts")
            continue
        if not in_facts:
            continue
        match = _LORE_FACT_RE.match(stripped)
        if not match:
            continue
        text = match.group(1).strip()
        source = (match.group(2) or "manual").strip()
        if text:
            results.append(LoreFact(text=text, source=source, file=canon))
    return results
```

- [ ] **Step 4: Run the test, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_lore_facts_parses_canon -v
```

- [ ] **Step 5: Commit**

```bash
git add showbible/vault.py tests/test_showbible.py
git commit -m "feat(vault): add lore_facts reader"
```

---

### Task 5: `add_lore_fact` / `update_lore_fact` / `remove_lore_fact`

**Files:**
- Modify: `showbible/vault.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_showbible.py`:

```python
def test_lore_fact_round_trip(tmp_path: Path) -> None:
    from showbible.vault import add_lore_fact, lore_facts, remove_lore_fact, update_lore_fact

    vault = init_vault(tmp_path / "demo")

    add_lore_fact(vault, "The colony predates the founders.", source="manual")
    add_lore_fact(vault, "The bell rings only on the equinox.", source="S01E03")

    facts = [(f.text, f.source) for f in lore_facts(vault)]
    assert ("The colony predates the founders.", "manual") in facts
    assert ("The bell rings only on the equinox.", "S01E03") in facts

    update_lore_fact(
        vault,
        original_text="The colony predates the founders.",
        new_text="The colony predates every founder.",
        new_source="S01E04",
    )

    after_update = [(f.text, f.source) for f in lore_facts(vault)]
    assert ("The colony predates every founder.", "S01E04") in after_update
    assert ("The colony predates the founders.", "manual") not in after_update

    remove_lore_fact(vault, "The bell rings only on the equinox.")

    after_remove = [f.text for f in lore_facts(vault)]
    assert "The bell rings only on the equinox." not in after_remove
    assert "The colony predates every founder." in after_remove
```

- [ ] **Step 2: Run, expect ImportError**

```bash
python -m pytest tests/test_showbible.py::test_lore_fact_round_trip -v
```

- [ ] **Step 3: Implement in `showbible/vault.py`**

```python
def _canon_path(vault: Path) -> Path:
    return vault / "lore-bible" / "canon.md"


def _lore_line(text: str, source: str) -> str:
    return f"- **Manual fact** - {text.strip()} *Source: {source.strip() or 'manual'}*"


def add_lore_fact(vault: Path, text: str, *, source: str = "manual") -> Path:
    path = _canon_path(vault)
    body = path.read_text(encoding="utf-8") if path.exists() else "# Canon\n\n## Facts\n\n"
    if "## Facts" not in body:
        body = body.rstrip() + "\n\n## Facts\n\n"
    body = body.rstrip() + "\n" + _lore_line(text, source) + "\n"
    atomic_write_text(path, body)
    return path


def update_lore_fact(
    vault: Path,
    *,
    original_text: str,
    new_text: str,
    new_source: str,
) -> Path:
    path = _canon_path(vault)
    if not path.exists():
        raise VaultError("canon.md missing")
    text = path.read_text(encoding="utf-8")
    new_body, count = _replace_lore_line(text, original_text, _lore_line(new_text, new_source))
    if count == 0:
        raise VaultError(f"lore fact not found: {original_text!r}")
    atomic_write_text(path, new_body)
    return path


def remove_lore_fact(vault: Path, text: str) -> Path:
    path = _canon_path(vault)
    if not path.exists():
        raise VaultError("canon.md missing")
    body = path.read_text(encoding="utf-8")
    new_body, count = _replace_lore_line(body, text, replacement=None)
    if count == 0:
        raise VaultError(f"lore fact not found: {text!r}")
    atomic_write_text(path, new_body)
    return path


def _replace_lore_line(
    text: str,
    fact: str,
    replacement: str | None,
) -> tuple[str, int]:
    pattern = re.compile(
        rf"^-\s*(?:\*\*Manual fact\*\*\s*-\s*)?{re.escape(fact.strip())}(?:\s*\*Source:[^*]*\*)?\s*$",
        flags=re.MULTILINE,
    )
    if replacement is None:
        new_text, count = pattern.subn("", text)
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        return new_text, count
    return pattern.subn(replacement, text)
```

- [ ] **Step 4: Run, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_lore_fact_round_trip -v
```

- [ ] **Step 5: Commit**

```bash
git add showbible/vault.py tests/test_showbible.py
git commit -m "feat(vault): add/update/remove_lore_fact helpers"
```

---

### Task 6: Refactor `cmd_lore_add` to use the helper

**Files:**
- Modify: `showbible/cli.py:523-530`

- [ ] **Step 1: Replace the function body**

```python
def cmd_lore_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    path = add_lore_fact(vault, args.fact, source=args.source)
    print(f"Added lore fact to {path}")
    return 0
```

Add `add_lore_fact` to the existing `from showbible.vault import …` block in `cli.py`.

- [ ] **Step 2: Run the lore-touching tests**

```bash
python -m pytest tests/test_showbible.py::test_episode_and_cast_commands tests/test_showbible.py::test_dashboard_actions_construct_show_without_leaving_workflow -v
```

Expected: both PASS — output text and on-disk format unchanged.

- [ ] **Step 3: Commit**

```bash
git add showbible/cli.py
git commit -m "refactor(cli): cmd_lore_add uses add_lore_fact helper"
```

---

### Task 7: `_generate_arc_suggestions` + `arcs suggest` CLI

Mirrors `_generate_cast_suggestions` / `cmd_cast_suggest`. The model returns a JSON array of `{episode, status, beat}` objects; on `ProviderError` we fall back to a small static seed. **No `--pick` flag** (the Textual `AISuggestScreen` covers the interactive pick path).

**Files:**
- Modify: `showbible/cli.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the happy-path test**

Append to `tests/test_showbible.py`:

```python
def test_arcs_suggest_applies_with_stub_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from showbible.vault import arc_beats

    vault = init_vault(tmp_path / "demo", show_name="Demo Show")

    class Provider:
        name = "stub"

        def generate(self, phase: str, episode_id: str, prompt: str):
            return type(
                "Generation",
                (),
                {
                    "text": '[{"episode":"S01E02","status":"planned","beat":"raise the stakes"},'
                            '{"episode":"S01E03","status":"planned","beat":"pay off the question"}]',
                    "tokens": 0,
                    "dollars": 0.0,
                },
            )()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(
        [
            "arcs",
            "suggest",
            "--vault",
            str(vault),
            "--episode",
            "S01E01",
            "--apply",
        ]
    ) == 0

    beats = [(b.episode, b.status, b.beat) for b in arc_beats(vault) if b.arc == "season-theme"]
    assert ("S01E02", "planned", "raise the stakes") in beats
    assert ("S01E03", "planned", "pay off the question") in beats
```

- [ ] **Step 2: Write the provider-failure fallback test**

Append:

```python
def test_arcs_suggest_falls_back_when_provider_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vault = init_vault(tmp_path / "demo", show_name="Demo Show")

    class Provider:
        name = "broken"

        def generate(self, phase: str, episode_id: str, prompt: str):
            raise ProviderError("offline")

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(
        ["arcs", "suggest", "--vault", str(vault), "--episode", "S01E01", "--json"]
    ) == 0

    output = capsys.readouterr().out
    assert "beat" in output
    raw = (vault / "episodes" / "S01E01" / "arc-suggestions-raw.md").read_text(encoding="utf-8")
    assert "Provider failed" in raw
```

- [ ] **Step 3: Run, expect failure (subcommand not yet defined)**

```bash
python -m pytest tests/test_showbible.py::test_arcs_suggest_applies_with_stub_provider tests/test_showbible.py::test_arcs_suggest_falls_back_when_provider_fails -v
```

Expected: argparse usage error.

- [ ] **Step 4: Add the subparser entry in `build_parser`**

Find the block defining the `arcs` subparser (around `cli.py:286-308`). Immediately after the `arcs_add.set_defaults(func=cmd_arcs_add)` line, add:

```python
    arcs_suggest = arcs_sub.add_parser("suggest", help="suggest arc beats with the AI provider")
    add_vault_flag(arcs_suggest)
    arcs_suggest.add_argument("--episode", help="episode scope; defaults from cwd or room state")
    arcs_suggest.add_argument("--arc", default="season-theme")
    arcs_suggest.add_argument("--provider", default="lmstudio")
    arcs_suggest.add_argument("--limit", type=int, default=6)
    arcs_suggest.add_argument("--apply", action="store_true")
    arcs_suggest.add_argument("--json", action="store_true")
    arcs_suggest.set_defaults(func=cmd_arcs_suggest)
```

- [ ] **Step 5: Implement `_generate_arc_suggestions`, `_apply_arc_suggestions`, `cmd_arcs_suggest`**

Add to `cli.py` near `_generate_cast_suggestions` (around line 1248):

```python
def _generate_arc_suggestions(
    vault: Path,
    episode_id: str | None,
    provider: str,
    arc_slug: str = "season-theme",
    limit: int = 6,
) -> list[dict[str, str]]:
    pack = (vault / "pack.yaml").read_text(encoding="utf-8")
    show_name = _show_name_from_pack(pack) or vault.name
    existing = [
        f"{b.episode} [{b.status}] {b.beat}"
        for b in arc_beats(vault)
        if b.arc == slugify(arc_slug)
    ]
    existing_line = "; ".join(existing) or "none"
    episode_context = f"\nFocus episode: {episode_id}" if episode_id else ""
    prompt = (
        f"Suggest up to {limit} new arc beats for {show_name} on the '{arc_slug}' arc. "
        "Return JSON only: an array of objects with keys episode (e.g. S01E02), "
        "status (planned|in-progress|done), and beat (one short sentence). "
        f"Do not repeat any of these existing beats: {existing_line}.{episode_context}\n\n"
        f"Current pack:\n{pack}"
    )
    suggestion_dir = (vault / "episodes" / episode_id) if episode_id else (vault / "research")
    suggestion_path = suggestion_dir / "arc-suggestions.md"
    raw_path = suggestion_dir / "arc-suggestions-raw.md"
    provider_obj = resolve_provider(provider)
    try:
        generation = provider_obj.generate("arc-suggest", "arcs", prompt)
        try:
            suggestions = _extract_json_array(generation.text)
        except ValueError:
            atomic_write_text(raw_path, generation.text + "\n")
            raise ValueError(f"AI arc suggestion did not return valid JSON. Raw output saved: {raw_path}")
    except ProviderError as exc:
        suggestions = _fallback_arc_suggestions(episode_id, limit)
        atomic_write_text(raw_path, f"Provider failed: {exc}\n")
    suggestions = _normalise_arc_suggestions(suggestions, default_episode=episode_id)
    atomic_write_text(
        suggestion_path,
        f"# Arc Suggestions for {arc_slug}\n\n```json\n{json.dumps(suggestions, indent=2)}\n```\n",
    )
    return suggestions


def _fallback_arc_suggestions(episode_id: str | None, limit: int) -> list[dict[str, str]]:
    target = episode_id or "S01E02"
    seeds = [
        {"episode": target, "status": "planned", "beat": "Raise the season's central question."},
        {"episode": target, "status": "planned", "beat": "Force the protagonist to take a side."},
        {"episode": target, "status": "planned", "beat": "Pay off a setup from the pilot."},
        {"episode": target, "status": "planned", "beat": "Introduce a complication for the antagonist."},
        {"episode": target, "status": "planned", "beat": "Reveal an unexpected ally."},
        {"episode": target, "status": "planned", "beat": "Set up the midseason turn."},
    ]
    return seeds[: max(1, limit)]


def _normalise_arc_suggestions(
    suggestions: list[dict[str, object]],
    default_episode: str | None,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for entry in suggestions:
        if not isinstance(entry, dict):
            continue
        beat = str(entry.get("beat", "")).strip()
        if not beat:
            continue
        cleaned.append(
            {
                "episode": str(entry.get("episode") or default_episode or "S01E01").upper(),
                "status": str(entry.get("status") or "planned").strip() or "planned",
                "beat": beat,
            }
        )
    return cleaned


def _apply_arc_suggestions(
    vault: Path,
    arc_slug: str,
    suggestions: list[dict[str, str]],
) -> int:
    for entry in suggestions:
        add_arc_beat(vault, arc_slug, entry["episode"], entry["status"], entry["beat"])
    return len(suggestions)


def cmd_arcs_suggest(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _arc_episode_scope(vault, args)
    suggestions = _generate_arc_suggestions(
        vault, episode_id, args.provider, arc_slug=args.arc, limit=args.limit
    )
    if args.apply:
        applied = _apply_arc_suggestions(vault, args.arc, suggestions)
        print(f"Applied {applied} arc beat suggestion(s) to {args.arc}.")
    elif args.json:
        print(json.dumps(suggestions, indent=2, sort_keys=True))
    else:
        print(json.dumps(suggestions, indent=2))
    return 0
```

Add `arc_beats`, `add_arc_beat`, and `slugify` to the existing `from showbible.vault import …` block in `cli.py` if not already present.

- [ ] **Step 6: Run the new tests, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_arcs_suggest_applies_with_stub_provider tests/test_showbible.py::test_arcs_suggest_falls_back_when_provider_fails -v
```

- [ ] **Step 7: Run the full suite**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add showbible/cli.py tests/test_showbible.py
git commit -m "feat(cli): add 'arcs suggest' AI command"
```

---

### Task 8: `_generate_lore_suggestions` + `lore suggest` CLI

Same shape as Task 7, for facts.

**Files:**
- Modify: `showbible/cli.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the tests**

Append to `tests/test_showbible.py`:

```python
def test_lore_suggest_applies_with_stub_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from showbible.vault import lore_facts

    vault = init_vault(tmp_path / "demo", show_name="Demo Show")

    class Provider:
        name = "stub"

        def generate(self, phase: str, episode_id: str, prompt: str):
            return type(
                "Generation",
                (),
                {
                    "text": '[{"fact":"The crown is older than the kingdom."},'
                            '{"fact":"Only the seer remembers the founding name."}]',
                    "tokens": 0,
                    "dollars": 0.0,
                },
            )()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(
        ["lore", "suggest", "--vault", str(vault), "--episode", "S01E01", "--apply"]
    ) == 0

    facts = [f.text for f in lore_facts(vault)]
    assert "The crown is older than the kingdom." in facts
    assert "Only the seer remembers the founding name." in facts


def test_lore_suggest_falls_back_when_provider_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vault = init_vault(tmp_path / "demo", show_name="Demo Show")

    class Provider:
        name = "broken"

        def generate(self, phase: str, episode_id: str, prompt: str):
            raise ProviderError("offline")

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(
        ["lore", "suggest", "--vault", str(vault), "--episode", "S01E01", "--json"]
    ) == 0

    output = capsys.readouterr().out
    assert "fact" in output
    raw = (vault / "episodes" / "S01E01" / "lore-suggestions-raw.md").read_text(encoding="utf-8")
    assert "Provider failed" in raw
```

- [ ] **Step 2: Run, expect failure**

```bash
python -m pytest tests/test_showbible.py::test_lore_suggest_applies_with_stub_provider tests/test_showbible.py::test_lore_suggest_falls_back_when_provider_fails -v
```

- [ ] **Step 3: Add the subparser entry in `build_parser`**

After the existing `lore_paths.set_defaults(func=cmd_lore_paths)` line in `build_parser`, add:

```python
    lore_suggest = lore_sub.add_parser("suggest", help="suggest canon facts with the AI provider")
    add_vault_flag(lore_suggest)
    lore_suggest.add_argument("--episode", help="episode scope; defaults from cwd or room state")
    lore_suggest.add_argument("--provider", default="lmstudio")
    lore_suggest.add_argument("--limit", type=int, default=6)
    lore_suggest.add_argument("--apply", action="store_true")
    lore_suggest.add_argument("--json", action="store_true")
    lore_suggest.set_defaults(func=cmd_lore_suggest)
```

- [ ] **Step 4: Implement `_generate_lore_suggestions`, `_apply_lore_suggestions`, `cmd_lore_suggest`**

Add to `cli.py`:

```python
def _generate_lore_suggestions(
    vault: Path,
    episode_id: str | None,
    provider: str,
    limit: int = 6,
) -> list[dict[str, str]]:
    pack = (vault / "pack.yaml").read_text(encoding="utf-8")
    show_name = _show_name_from_pack(pack) or vault.name
    existing = [f.text for f in lore_facts(vault)]
    existing_line = "; ".join(existing) or "none"
    episode_context = f"\nEpisode scope: {episode_id}" if episode_id else ""
    prompt = (
        f"Suggest up to {limit} new canon facts for {show_name}. "
        "Return JSON only: an array of objects with key 'fact' (one short sentence each). "
        f"Do not repeat any of these established facts: {existing_line}.{episode_context}\n\n"
        f"Current pack:\n{pack}"
    )
    suggestion_dir = (vault / "episodes" / episode_id) if episode_id else (vault / "research")
    suggestion_path = suggestion_dir / "lore-suggestions.md"
    raw_path = suggestion_dir / "lore-suggestions-raw.md"
    provider_obj = resolve_provider(provider)
    try:
        generation = provider_obj.generate("lore-suggest", "lore", prompt)
        try:
            suggestions = _extract_json_array(generation.text)
        except ValueError:
            atomic_write_text(raw_path, generation.text + "\n")
            raise ValueError(f"AI lore suggestion did not return valid JSON. Raw output saved: {raw_path}")
    except ProviderError as exc:
        suggestions = _fallback_lore_suggestions(show_name, limit)
        atomic_write_text(raw_path, f"Provider failed: {exc}\n")
    suggestions = _normalise_lore_suggestions(suggestions)
    atomic_write_text(
        suggestion_path,
        f"# Lore Suggestions for {show_name}\n\n```json\n{json.dumps(suggestions, indent=2)}\n```\n",
    )
    return suggestions


def _fallback_lore_suggestions(show_name: str, limit: int) -> list[dict[str, str]]:
    seeds = [
        {"fact": f"{show_name} is set in a world where memory is currency."},
        {"fact": "The founding charter is rewritten by every generation."},
        {"fact": "The protagonists' guild predates the city by a century."},
        {"fact": "A locked archive holds the names that must not be spoken."},
        {"fact": "An eclipse marks every legal succession."},
        {"fact": "The seer's apprentice never inherits the title."},
    ]
    return seeds[: max(1, limit)]


def _normalise_lore_suggestions(
    suggestions: list[dict[str, object]],
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for entry in suggestions:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("fact", "")).strip()
        if text:
            cleaned.append({"fact": text})
    return cleaned


def _apply_lore_suggestions(
    vault: Path,
    suggestions: list[dict[str, str]],
    source: str,
) -> int:
    for entry in suggestions:
        add_lore_fact(vault, entry["fact"], source=source)
    return len(suggestions)


def cmd_lore_suggest(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = args.episode or _current_episode(vault)
    suggestions = _generate_lore_suggestions(vault, episode_id, args.provider, limit=args.limit)
    if args.apply:
        applied = _apply_lore_suggestions(vault, suggestions, source=episode_id or "manual")
        print(f"Applied {applied} lore fact suggestion(s).")
    elif args.json:
        print(json.dumps(suggestions, indent=2, sort_keys=True))
    else:
        print(json.dumps(suggestions, indent=2))
    return 0
```

Add `lore_facts` and `add_lore_fact` to the `from showbible.vault import …` block.

- [ ] **Step 5: Run, expect PASS + full suite green**

```bash
python -m pytest tests/test_showbible.py::test_lore_suggest_applies_with_stub_provider tests/test_showbible.py::test_lore_suggest_falls_back_when_provider_fails -v
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add showbible/cli.py tests/test_showbible.py
git commit -m "feat(cli): add 'lore suggest' AI command"
```

---

## Stage 2 — Textual scaffolding

### Task 9: `AppState` dataclass + `refresh_from_disk`

**Files:**
- Create: `showbible/tui/__init__.py`
- Create: `showbible/tui/state.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_showbible.py`:

```python
def test_app_state_refresh_from_disk(tmp_path: Path) -> None:
    from showbible.tui.state import AppState
    from showbible.vault import add_arc_beat, add_lore_fact

    vault = init_vault(tmp_path / "demo", show_name="Demo Show")
    add_arc_beat(vault, "season-theme", "S01E01", "planned", "open the season")
    add_lore_fact(vault, "The colony predates the founders.", source="S01E01")

    state = AppState.empty(vault=vault, current_episode="S01E01").refreshed_from_disk()

    assert state.show_name == "Demo Show"
    assert state.current_episode == "S01E01"
    assert "S01E01" in state.episodes
    assert any(b.beat == "open the season" for b in state.arc_beats)
    assert any(f.text == "The colony predates the founders." for f in state.lore_facts)
    assert state.runs == {}
```

- [ ] **Step 2: Run, expect ImportError**

```bash
python -m pytest tests/test_showbible.py::test_app_state_refresh_from_disk -v
```

- [ ] **Step 3: Create `showbible/tui/__init__.py`**

```python
"""Textual TUI for ShowBible."""
```

- [ ] **Step 4: Create `showbible/tui/state.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from showbible.cli import _show_name_from_pack
from showbible.vault import (
    ArcBeat,
    CastRole,
    DoctorFinding,
    LoreFact,
    arc_beats,
    doctor,
    effective_cast_roles,
    list_episodes,
    lore_facts,
    read_json,
)


@dataclass(frozen=True)
class AppState:
    vault: Path
    show_name: str
    current_episode: str
    episodes: list[str]
    cast: list[CastRole]
    arc_beats: list[ArcBeat]
    lore_facts: list[LoreFact]
    doctor_findings: list[DoctorFinding]
    costs: dict
    last_action: str
    runs: dict  # dict[str, RunHandle] but typed loosely to avoid an import cycle

    @classmethod
    def empty(cls, *, vault: Path, current_episode: str) -> "AppState":
        return cls(
            vault=vault,
            show_name=vault.name,
            current_episode=current_episode,
            episodes=[],
            cast=[],
            arc_beats=[],
            lore_facts=[],
            doctor_findings=[],
            costs={},
            last_action="",
            runs={},
        )

    def refreshed_from_disk(self) -> "AppState":
        pack_path = self.vault / "pack.yaml"
        show_name = self.vault.name
        if pack_path.exists():
            show_name = _show_name_from_pack(pack_path.read_text(encoding="utf-8")) or self.vault.name
        return replace(
            self,
            show_name=show_name,
            episodes=list_episodes(self.vault),
            cast=effective_cast_roles(self.vault, self.current_episode),
            arc_beats=arc_beats(self.vault),
            lore_facts=lore_facts(self.vault),
            doctor_findings=doctor(self.vault),
            costs=read_json(self.vault / ".room" / "costs.json", {}),
        )

    def with_episode(self, episode_id: str) -> "AppState":
        return replace(self, current_episode=episode_id).refreshed_from_disk()

    def with_action(self, message: str) -> "AppState":
        return replace(self, last_action=message)

    def with_runs(self, runs: dict) -> "AppState":
        return replace(self, runs=runs)
```

- [ ] **Step 5: Run, expect PASS + full suite green**

```bash
python -m pytest tests/test_showbible.py::test_app_state_refresh_from_disk -v
python -m pytest tests/test_showbible.py 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add showbible/tui/__init__.py showbible/tui/state.py tests/test_showbible.py
git commit -m "feat(tui): add AppState with refresh_from_disk"
```

---

### Task 10: `RunHandle` + `RunRegistry` + progress bridge

**Files:**
- Create: `showbible/tui/runs.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_showbible.py`:

```python
def test_run_registry_tracks_progress() -> None:
    from collections import deque

    from showbible.tui.runs import RunHandle, RunRegistry

    registry = RunRegistry()

    handle = registry.start("S01E01")
    assert handle.episode_id == "S01E01"
    assert handle.status == "running"
    assert handle.run_id in registry.handles

    registry.on_progress(handle.run_id, "started", "pitch", {})
    assert registry.handles[handle.run_id].current_phase == "pitch"

    registry.on_progress(handle.run_id, "completed", "pitch", {"tokens": 12})
    assert "pitch" in registry.handles[handle.run_id].completed_phases
    assert registry.handles[handle.run_id].tokens == 12

    registry.on_progress(handle.run_id, "skipped", "break", {})
    assert "break" in registry.handles[handle.run_id].skipped_phases

    registry.on_completed(handle.run_id, message="Ran S01E01")
    assert registry.handles[handle.run_id].status == "complete"

    failure = registry.start("S01E02")
    registry.on_failed(failure.run_id, error="boom")
    assert registry.handles[failure.run_id].status == "failed"
    assert registry.handles[failure.run_id].error == "boom"

    assert isinstance(registry.handles[handle.run_id].log_tail, deque)
```

- [ ] **Step 2: Run, expect ImportError**

```bash
python -m pytest tests/test_showbible.py::test_run_registry_tracks_progress -v
```

- [ ] **Step 3: Create `showbible/tui/runs.py`**

```python
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class RunHandle:
    run_id: str
    episode_id: str
    started_at: float
    status: str = "running"
    current_phase: str | None = None
    completed_phases: list[str] = field(default_factory=list)
    skipped_phases: list[str] = field(default_factory=list)
    tokens: int = 0
    dollars: float = 0.0
    error: str | None = None
    log_tail: deque[str] = field(default_factory=lambda: deque(maxlen=100))


class RunRegistry:
    def __init__(self) -> None:
        self.handles: dict[str, RunHandle] = {}

    def start(self, episode_id: str) -> RunHandle:
        run_id = uuid.uuid4().hex[:8]
        handle = RunHandle(run_id=run_id, episode_id=episode_id, started_at=time.time())
        self.handles[run_id] = handle
        return handle

    def on_progress(self, run_id: str, event: str, phase: str, payload: dict[str, Any]) -> None:
        handle = self.handles.get(run_id)
        if handle is None:
            return
        if event in {"started", "episode-started"}:
            handle.current_phase = phase
            handle.log_tail.append(f"[{phase}] {event}")
        elif event == "completed":
            if phase not in handle.completed_phases:
                handle.completed_phases.append(phase)
            tokens = int(payload.get("tokens", 0) or 0)
            handle.tokens += tokens
            handle.log_tail.append(f"[{phase}] completed ({tokens} tokens)")
        elif event == "skipped":
            if phase not in handle.skipped_phases:
                handle.skipped_phases.append(phase)
            handle.log_tail.append(f"[{phase}] skipped")
        elif event == "episode-completed":
            handle.log_tail.append(f"[{phase}] episode complete")

    def on_completed(self, run_id: str, *, message: str) -> None:
        handle = self.handles.get(run_id)
        if handle is None:
            return
        handle.status = "complete"
        handle.log_tail.append(message)

    def on_failed(self, run_id: str, *, error: str) -> None:
        handle = self.handles.get(run_id)
        if handle is None:
            return
        handle.status = "failed"
        handle.error = error
        handle.log_tail.append(f"FAILED: {error}")

    def snapshot(self) -> dict[str, RunHandle]:
        return {run_id: replace(handle, log_tail=deque(handle.log_tail, maxlen=100))
                for run_id, handle in self.handles.items()}
```

- [ ] **Step 4: Run, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_run_registry_tracks_progress -v
```

- [ ] **Step 5: Commit**

```bash
git add showbible/tui/runs.py tests/test_showbible.py
git commit -m "feat(tui): add RunHandle and RunRegistry"
```

---

### Task 11: `Sidebar` widget (NAVIGATE/COMMAND/ACTIVE RUNS sections)

**Files:**
- Create: `showbible/tui/widgets/__init__.py`
- Create: `showbible/tui/widgets/sidebar.py`

- [ ] **Step 1: Create `showbible/tui/widgets/__init__.py`**

```python
"""Reusable Textual widgets for ShowBible."""
```

- [ ] **Step 2: Create `showbible/tui/widgets/sidebar.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

NAV_OPTIONS = [
    ("episodes", "Episodes"),
    ("cast", "Cast"),
    ("arc", "Arc"),
    ("lore", "Lore"),
    ("outputs", "Outputs"),
]

COMMAND_OPTIONS = [
    ("run", "Run"),       # label is updated dynamically by ShowBibleApp
    ("snapshot", "Snapshot"),
    ("doctor", "Doctor"),
    ("quit", "Quit"),
]


@dataclass
class SidebarSelection(Message):
    section: str  # "nav" | "command" | "run"
    key: str


class Sidebar(Vertical):
    DEFAULT_CSS = """
    Sidebar {
        width: 28;
        border-right: solid $accent;
        padding: 1;
    }
    Sidebar > Label {
        color: $accent;
        text-style: bold;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="sidebar")
        self._nav = OptionList(
            *(Option(label, id=key) for key, label in NAV_OPTIONS),
            id="sidebar-nav",
        )
        self._command = OptionList(
            *(Option(label, id=key) for key, label in COMMAND_OPTIONS),
            id="sidebar-command",
        )
        self._runs = OptionList(id="sidebar-runs")

    def compose(self):
        yield Label("NAVIGATE")
        yield self._nav
        yield Label("COMMAND")
        yield self._command
        yield Label("ACTIVE RUNS")
        yield self._runs

    def on_mount(self) -> None:
        self._nav.highlighted = 0

    def update_run_label(self, episode_id: str) -> None:
        self._command.replace_option_prompt_at_index(0, f"Run {episode_id}")

    def update_active_runs(self, runs: dict) -> None:
        self._runs.clear_options()
        for run_id, handle in runs.items():
            phase = handle.current_phase or "starting"
            done = len(handle.completed_phases)
            label = f"● {handle.episode_id} ({done}/6 · {phase})"
            if handle.status == "complete":
                label = f"✓ {handle.episode_id} done"
            elif handle.status == "failed":
                label = f"✗ {handle.episode_id} failed"
            self._runs.add_option(Option(label, id=run_id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self._nav:
            self.post_message(SidebarSelection(section="nav", key=event.option.id))
        elif event.option_list is self._command:
            self.post_message(SidebarSelection(section="command", key=event.option.id))
        elif event.option_list is self._runs:
            self.post_message(SidebarSelection(section="run", key=event.option.id))
        event.stop()
```

- [ ] **Step 3: Smoke import check**

```bash
python -c "from showbible.tui.widgets.sidebar import Sidebar, SidebarSelection; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add showbible/tui/widgets/__init__.py showbible/tui/widgets/sidebar.py
git commit -m "feat(tui): add Sidebar widget"
```

---

### Task 12: Minimal `ShowBibleApp` shell + boot Pilot test

This task wires the App skeleton with a placeholder content area (no real panes yet — those come in Stage 3). The point is to prove the app boots, the sidebar mounts, and the timer poll updates `AppState`.

**Files:**
- Create: `showbible/tui/app.py`
- Create: `tests/test_tui_smoke.py`

- [ ] **Step 1: Write the failing Pilot test**

Create `tests/test_tui_smoke.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from showbible.vault import init_vault


@pytest.mark.asyncio
async def test_app_boots_and_shows_sidebar(tmp_path: Path) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.widgets.sidebar import Sidebar

    vault = init_vault(tmp_path / "demo")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(Sidebar)
        assert sidebar is not None
        assert app.state.show_name == vault.name
        assert app.state.current_episode == "S01E01"
        assert "S01E01" in app.state.episodes
```

- [ ] **Step 2: Run, expect ImportError**

```bash
python -m pytest tests/test_tui_smoke.py::test_app_boots_and_shows_sidebar -v
```

- [ ] **Step 3: Create `showbible/tui/app.py`**

```python
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from showbible.tui.runs import RunRegistry
from showbible.tui.state import AppState
from showbible.tui.widgets.sidebar import Sidebar, SidebarSelection


class ShowBibleApp(App):
    CSS = """
    Screen { layout: vertical; }
    #header-bar { height: 1; padding: 0 1; background: $accent 30%; }
    Horizontal#main { height: 1fr; }
    #content { padding: 1 2; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    state: reactive[AppState] = reactive(None, init=False)

    def __init__(self, *, vault: Path, episode_id: str, provider: str) -> None:
        super().__init__()
        self._vault = vault
        self._episode_id = episode_id
        self._provider = provider
        self._registry = RunRegistry()
        self.state = AppState.empty(vault=vault, current_episode=episode_id).refreshed_from_disk()

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header-bar")
        with Horizontal(id="main"):
            yield Sidebar()
            yield Static("Select Episodes from the sidebar to begin.", id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self.state = self.state.refreshed_from_disk().with_runs(self._registry.snapshot())
        self._update_chrome()

    def _update_chrome(self) -> None:
        self.query_one("#header-bar", Static).update(self._header_text())
        sidebar = self.query_one(Sidebar)
        sidebar.update_run_label(self.state.current_episode)
        sidebar.update_active_runs(self.state.runs)

    def _header_text(self) -> str:
        return (
            f"ShowBible · {self.state.show_name} · vault: {self._vault}"
            f" · {self.state.current_episode}"
        )

    def action_refresh(self) -> None:
        self._tick()

    def on_sidebar_selection(self, message: SidebarSelection) -> None:
        if message.section == "command" and message.key == "quit":
            self.exit(0)
```

- [ ] **Step 4: Run the smoke test, expect PASS**

```bash
python -m pytest tests/test_tui_smoke.py::test_app_boots_and_shows_sidebar -v
```

Expected: PASS.

- [ ] **Step 5: Run the full suite**

```bash
python -m pytest 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add showbible/tui/app.py tests/test_tui_smoke.py
git commit -m "feat(tui): add ShowBibleApp shell with sidebar and timer poll"
```

---

### Task 13: Replace `cmd_tui` body and delete the curses dashboard

**Files:**
- Modify: `showbible/cli.py` — large delete + `cmd_tui` rewrite
- Modify: `tests/test_showbible.py` — drop tests that depend on deleted helpers

- [ ] **Step 1: Inventory the soon-to-be-deleted symbols**

```bash
grep -nE "^def (_workflow_tui|_dashboard_actions|_run_dashboard_action|_run_dashboard_live|_format_run_event|_draw_run_progress|_dashboard_panel_lines|_dashboard_prompt|_prompt_dashboard_line|_episodes_tui|_cast_tui|_episode_outputs_tui|_arc_tui|_lore_tui|_arc_suggest_tui|_lore_suggest_tui|_cast_suggest_tui|_pick_items_screen|_pick_cast_suggestions)\b" /Users/eric/code/showbible.io/showbible/cli.py
```

Expected: a printout of definitions. Note line ranges.

- [ ] **Step 2: Delete all the listed function bodies from `showbible/cli.py`**

Open `showbible/cli.py` and delete the entire bodies of every function listed in Step 1. Also delete the `_arc_suggest_tui` / `_lore_suggest_tui` stubs if they exist. Delete the `import curses` and `import threading` lines at the top of `cli.py` (they are no longer used — `RunRegistry`'s threading is in `tui/runs.py`).

After deletion, `cli.py` should still import cleanly. Verify:

```bash
python -c "import showbible.cli; print('ok')"
```

Expected: `ok`. If you get a `NameError`, you removed an import but a remaining function still references it; restore the import or remove the dangling reference.

- [ ] **Step 3: Replace `cmd_tui` body**

Find `cmd_tui` (look for `def cmd_tui(` — there is exactly one). Replace the function with:

```python
def cmd_tui(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = args.episode or _current_episode(vault) or "S01E01"
    ensure_episode(vault, episode_id)
    _write_room_state(vault, "planning", episode_id=episode_id)
    if args.no_tui or not (sys.stdin.isatty() and sys.stdout.isatty()):
        _print_workflow_snapshot(vault, episode_id, args.provider)
        return 0
    from showbible.tui.app import ShowBibleApp
    return ShowBibleApp(vault=vault, episode_id=episode_id, provider=args.provider).run() or 0
```

- [ ] **Step 4: Replace `cmd_workflow` body to mirror `cmd_tui`**

`cmd_workflow` is a near-duplicate. Replace its body with:

```python
def cmd_workflow(args: argparse.Namespace) -> int:
    return cmd_tui(args)
```

- [ ] **Step 5: Delete tests that exercised deleted functions**

In `tests/test_showbible.py`, delete the entire `test_dashboard_actions_construct_show_without_leaving_workflow` function (it tested `_run_dashboard_action`, which is gone) and the entire `test_run_progress_event_text_is_visible` function (it tested `_format_run_event`, gone). Also delete `test_episode_editor_key_hints_match_behavior` if present (it asserts curses key bindings on the deleted editor). Adjust the imports at the top of the test file: remove `_format_run_event` and `_run_dashboard_action` from the `from showbible.cli import …` block.

- [ ] **Step 6: Run the suite**

```bash
python -m pytest 2>&1 | tail -10
```

Expected: green. Tests that touched deleted behaviour are gone; the remaining suite passes plus the Pilot smoke test from Task 12.

- [ ] **Step 7: Smoke the CLI surface**

```bash
python -m showbible --help > /dev/null
python -m showbible tui --help > /dev/null
```

Expected: each exits 0.

- [ ] **Step 8: Commit**

```bash
git add showbible/cli.py tests/test_showbible.py
git commit -m "refactor(cli): delete curses dashboard, route cmd_tui to ShowBibleApp"
```

---

## Stage 3 — Panes

Each pane is a `Widget` mounted into the `#content` container. The base pane provides the standard list-and-detail layout. Concrete panes plug in their data source (a slice of `AppState`) and their hotkeys.

### Task 14: `BasePane` shell

**Files:**
- Create: `showbible/tui/panes/__init__.py`
- Create: `showbible/tui/panes/base.py`

- [ ] **Step 1: Create `showbible/tui/panes/__init__.py`**

```python
"""Content panes for ShowBible."""
```

- [ ] **Step 2: Create `showbible/tui/panes/base.py`**

```python
from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Static


class BasePane(Horizontal):
    DEFAULT_CSS = """
    BasePane { height: 1fr; }
    BasePane > Vertical { width: 50%; padding: 0 1; }
    BasePane #pane-list { border-right: solid $accent; }
    """

    def compose(self):
        with Vertical(id="pane-list"):
            yield from self.compose_list()
        with Vertical(id="pane-detail"):
            yield from self.compose_detail()

    def compose_list(self):
        yield Static("(empty)", id="pane-list-empty")

    def compose_detail(self):
        yield Static("Select an item.", id="pane-detail-empty")

    def refresh_from_state(self, state) -> None:
        """Override in subclasses to repopulate from AppState."""
```

- [ ] **Step 3: Smoke import**

```bash
python -c "from showbible.tui.panes.base import BasePane; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add showbible/tui/panes/__init__.py showbible/tui/panes/base.py
git commit -m "feat(tui): add BasePane skeleton"
```

---

### Task 15: `EpisodesPane`

**Files:**
- Create: `showbible/tui/panes/episodes.py`
- Modify: `showbible/tui/app.py` (mount as default content)

- [ ] **Step 1: Create `showbible/tui/panes/episodes.py`**

```python
from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


class EpisodeSelected(Message):
    def __init__(self, episode_id: str) -> None:
        super().__init__()
        self.episode_id = episode_id


class EpisodesPane(BasePane):
    BINDINGS = [
        Binding("n", "new", "New episode"),
    ]

    current_episode: reactive[str] = reactive("S01E01")

    def __init__(self) -> None:
        super().__init__(id="episodes-pane")
        self._list = OptionList(id="episodes-list")
        self._detail = Static("Select an episode.", id="episodes-detail")

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        self._list.clear_options()
        for ep in state.episodes:
            marker = "▶ " if ep == state.current_episode else "  "
            self._list.add_option(Option(f"{marker}{ep}", id=ep))
        self._list.add_option(Option("+ New episode", id="__new__"))
        self.current_episode = state.current_episode
        self._render_detail(state)

    def _render_detail(self, state) -> None:
        from showbible.vault import episode_meta
        ep_dir = state.vault / "episodes" / state.current_episode
        meta = episode_meta(ep_dir) if ep_dir.exists() else {}
        self._detail.update(
            f"episode: {state.current_episode}\n"
            f"status: {meta.get('status', 'created')}\n"
            f"completed phases: {len(meta.get('completed_phases', []))}\n"
            f"cast overrides: {len(meta.get('cast_overrides', []))}"
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__new__":
            self.action_new()
        else:
            self.post_message(EpisodeSelected(event.option.id))
        event.stop()

    def action_new(self) -> None:
        from showbible.cli import _next_episode_id
        from showbible.vault import ensure_episode, list_episodes
        new_id = _next_episode_id(list_episodes(self.app.state.vault))
        ensure_episode(self.app.state.vault, new_id)
        self.post_message(EpisodeSelected(new_id))
```

- [ ] **Step 2: Mount `EpisodesPane` in `ShowBibleApp` as the default content**

Edit `showbible/tui/app.py`. Replace the placeholder Static in `compose`:

```python
            yield Static("Select Episodes from the sidebar to begin.", id="content")
```

with:

```python
            yield EpisodesPane()
```

Add this import at the top of `app.py`:

```python
from showbible.tui.panes.episodes import EpisodesPane, EpisodeSelected
```

Add an `on_mount` populate call after the existing `on_mount` body:

```python
    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._populate_panes()

    def _populate_panes(self) -> None:
        for pane in self.query(BasePane):
            pane.refresh_from_state(self.state)
```

Import `BasePane` at the top:

```python
from showbible.tui.panes.base import BasePane
```

Update `_tick` to also re-populate panes:

```python
    def _tick(self) -> None:
        self.state = self.state.refreshed_from_disk().with_runs(self._registry.snapshot())
        self._update_chrome()
        self._populate_panes()
```

Handle `EpisodeSelected` so the app updates `current_episode`:

```python
    def on_episode_selected(self, message: EpisodeSelected) -> None:
        self.state = self.state.with_episode(message.episode_id)
        self._write_room_state()
        self._update_chrome()
        self._populate_panes()

    def _write_room_state(self) -> None:
        from showbible.cli import _write_room_state
        _write_room_state(self._vault, "planning", episode_id=self.state.current_episode)
```

- [ ] **Step 3: Add a Pilot test**

Append to `tests/test_tui_smoke.py`:

```python
@pytest.mark.asyncio
async def test_episodes_pane_lists_episodes(tmp_path: Path) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.panes.episodes import EpisodesPane

    vault = init_vault(tmp_path / "demo")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(EpisodesPane)
        list_widget = app.query_one("#episodes-list")
        assert list_widget.option_count >= 1
        assert any("S01E01" in str(opt.prompt) for opt in list_widget._options)
```

- [ ] **Step 4: Run the test**

```bash
python -m pytest tests/test_tui_smoke.py::test_episodes_pane_lists_episodes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add showbible/tui/panes/episodes.py showbible/tui/app.py tests/test_tui_smoke.py
git commit -m "feat(tui): add EpisodesPane and mount as default content"
```

---

### Task 16: `CastPane`

**Files:**
- Create: `showbible/tui/panes/cast.py`

- [ ] **Step 1: Create `showbible/tui/panes/cast.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class CastAction(Message):
    action: str  # "add" | "edit" | "delete" | "suggest"
    person_slug: str | None = None


class CastPane(BasePane):
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "suggest", "AI suggest"),
    ]

    def __init__(self) -> None:
        super().__init__(id="cast-pane")
        self._list = OptionList(id="cast-list")
        self._detail = Static("Select a cast member.", id="cast-detail")
        self._roles: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        from showbible.vault import people, episode_cast_roles
        self._roles = list(state.cast)
        people_by_slug = {p["slug"]: p for p in people(state.vault)}
        episode_overrides = {r.person for r in episode_cast_roles(state.vault, state.current_episode)}
        self._list.clear_options()
        for role in self._roles:
            tag = "[ep]" if role.person in episode_overrides else "[sh]"
            display = people_by_slug.get(role.person, {}).get("display_name", role.person)
            self._list.add_option(Option(f"{tag} {role.kind}: {display}", id=role.person))
        self._list.add_option(Option("+ Add new cast member", id="__add__"))
        self._render_detail(state)

    def _render_detail(self, state) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._roles):
            self._detail.update("Select a cast member or + Add.")
            return
        role = self._roles[idx]
        self._detail.update(
            f"kind: {role.kind}\n"
            f"person: {role.person}\n"
            f"plays: {role.plays or '-'}\n"
            f"file: people/{role.person}.md"
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail(self.app.state)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__add__":
            self.action_add()
        event.stop()

    def action_add(self) -> None:
        self.post_message(CastAction(action="add"))

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._roles):
            self.post_message(CastAction(action="edit", person_slug=self._roles[idx].person))

    def action_delete(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._roles):
            self.post_message(CastAction(action="delete", person_slug=self._roles[idx].person))

    def action_suggest(self) -> None:
        self.post_message(CastAction(action="suggest"))
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from showbible.tui.panes.cast import CastPane, CastAction; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/panes/cast.py
git commit -m "feat(tui): add CastPane (UI only, wiring follows)"
```

---

### Task 17: `ArcPane`

**Files:**
- Create: `showbible/tui/panes/arc.py`

- [ ] **Step 1: Create `showbible/tui/panes/arc.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class ArcAction(Message):
    action: str  # "add" | "edit" | "delete" | "suggest"
    arc_slug: str | None = None
    episode_id: str | None = None
    beat: str | None = None


class ArcPane(BasePane):
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "suggest", "AI suggest"),
    ]

    def __init__(self) -> None:
        super().__init__(id="arc-pane")
        self._list = OptionList(id="arc-list")
        self._detail = Static("Select an arc beat.", id="arc-detail")
        self._beats: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        self._beats = list(state.arc_beats)
        self._list.clear_options()
        for beat in self._beats:
            self._list.add_option(
                Option(f"[{beat.arc}] {beat.episode} [{beat.status}] {beat.beat}", id=f"{beat.arc}|{beat.episode}|{beat.beat}")
            )
        self._list.add_option(Option("+ Add new beat", id="__add__"))
        self._render_detail()

    def _render_detail(self) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._beats):
            self._detail.update("Add a new beat to any arc.")
            return
        beat = self._beats[idx]
        self._detail.update(
            f"arc: {beat.arc}\n"
            f"episode: {beat.episode}\n"
            f"status: {beat.status}\n"
            f"beat: {beat.beat}\n"
            f"file: arcs/{beat.arc}.md"
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__add__":
            self.action_add()
        event.stop()

    def action_add(self) -> None:
        self.post_message(ArcAction(action="add"))

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._beats):
            beat = self._beats[idx]
            self.post_message(ArcAction(action="edit", arc_slug=beat.arc, episode_id=beat.episode, beat=beat.beat))

    def action_delete(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._beats):
            beat = self._beats[idx]
            self.post_message(ArcAction(action="delete", arc_slug=beat.arc, episode_id=beat.episode, beat=beat.beat))

    def action_suggest(self) -> None:
        idx = self._list.highlighted or 0
        slug = self._beats[idx].arc if idx < len(self._beats) else "season-theme"
        self.post_message(ArcAction(action="suggest", arc_slug=slug))
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from showbible.tui.panes.arc import ArcPane, ArcAction; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/panes/arc.py
git commit -m "feat(tui): add ArcPane"
```

---

### Task 18: `LorePane`

**Files:**
- Create: `showbible/tui/panes/lore.py`

- [ ] **Step 1: Create `showbible/tui/panes/lore.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class LoreAction(Message):
    action: str  # "add" | "edit" | "delete" | "suggest"
    fact_text: str | None = None


class LorePane(BasePane):
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "suggest", "AI suggest"),
    ]

    def __init__(self) -> None:
        super().__init__(id="lore-pane")
        self._list = OptionList(id="lore-list")
        self._detail = Static("Select a fact.", id="lore-detail")
        self._facts: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        self._facts = list(state.lore_facts)
        self._list.clear_options()
        for fact in self._facts:
            self._list.add_option(Option(fact.text, id=fact.text))
        self._list.add_option(Option("+ Add new fact", id="__add__"))
        self._render_detail()

    def _render_detail(self) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._facts):
            self._detail.update("Add a new canon fact.")
            return
        fact = self._facts[idx]
        self._detail.update(
            f"fact: {fact.text}\n"
            f"source: {fact.source}\n"
            "file: lore-bible/canon.md"
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__add__":
            self.action_add()
        event.stop()

    def action_add(self) -> None:
        self.post_message(LoreAction(action="add"))

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._facts):
            self.post_message(LoreAction(action="edit", fact_text=self._facts[idx].text))

    def action_delete(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._facts):
            self.post_message(LoreAction(action="delete", fact_text=self._facts[idx].text))

    def action_suggest(self) -> None:
        self.post_message(LoreAction(action="suggest"))
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from showbible.tui.panes.lore import LorePane, LoreAction; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/panes/lore.py
git commit -m "feat(tui): add LorePane"
```

---

### Task 19: `OutputsPane` (Rich preview + `$EDITOR`)

**Files:**
- Create: `showbible/tui/panes/outputs.py`

- [ ] **Step 1: Create `showbible/tui/panes/outputs.py`**

```python
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from rich.markdown import Markdown
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class OutputAction(Message):
    action: str
    artifact: str | None = None


class OutputsPane(BasePane):
    BINDINGS = [
        Binding("e", "edit", "Edit in $EDITOR"),
        Binding("r", "refresh_preview", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__(id="outputs-pane")
        self._list = OptionList(id="outputs-list")
        self._preview = Static("Select an output.", id="outputs-preview")
        self._artifacts: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield VerticalScroll(self._preview)

    def refresh_from_state(self, state) -> None:
        from showbible.artifacts import list_episode_artifacts
        self._artifacts = list_episode_artifacts(state.vault, state.current_episode)
        self._list.clear_options()
        for art in self._artifacts:
            marker = "✓ " if art["exists"] else "· "
            self._list.add_option(Option(f"{marker}{art['name']}", id=art["name"]))
        self._render_preview(state)

    def _render_preview(self, state) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._artifacts):
            self._preview.update("Select an output.")
            return
        art = self._artifacts[idx]
        path = state.vault / "episodes" / state.current_episode / art["name"]
        if not path.exists():
            self._preview.update(f"(not yet generated: {art['name']})")
            return
        text = path.read_text(encoding="utf-8")
        self._preview.update(Markdown(text))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_preview(self.app.state)

    def action_refresh_preview(self) -> None:
        self._render_preview(self.app.state)

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._artifacts):
            return
        art = self._artifacts[idx]
        path = self.app.state.vault / "episodes" / self.app.state.current_episode / art["name"]
        editor = os.environ.get("EDITOR", "vi")
        with self.app.suspend():
            try:
                subprocess.run([editor, str(path)], check=False)
            except Exception as exc:  # noqa: BLE001
                self.notify(f"Editor failed: {exc}", severity="error")
        self._render_preview(self.app.state)
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from showbible.tui.panes.outputs import OutputsPane; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/panes/outputs.py
git commit -m "feat(tui): add OutputsPane with Rich preview and $EDITOR shell-out"
```

---

### Task 20: `RunDetailPane`

**Files:**
- Create: `showbible/tui/panes/run_detail.py`

- [ ] **Step 1: Create `showbible/tui/panes/run_detail.py`**

```python
from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

from showbible.engine import PHASES
from showbible.tui.panes.base import BasePane


class RunDetailPane(BasePane):
    def __init__(self, run_id: str) -> None:
        super().__init__(id=f"run-detail-{run_id}")
        self._run_id = run_id
        self._phases = Static("(no run yet)", id="run-detail-phases")
        self._log = Static("", id="run-detail-log")

    def compose_list(self):
        yield self._phases

    def compose_detail(self):
        yield VerticalScroll(self._log)

    def refresh_from_state(self, state) -> None:
        handle = state.runs.get(self._run_id)
        if handle is None:
            self._phases.update("(run not found)")
            return
        lines = []
        for phase in PHASES:
            if phase in handle.completed_phases:
                lines.append(f"[x] {phase}")
            elif phase == handle.current_phase:
                lines.append(f"[>] {phase}")
            elif phase in handle.skipped_phases:
                lines.append(f"[~] {phase} (skipped)")
            else:
                lines.append(f"[ ] {phase}")
        lines.append("")
        lines.append(f"status: {handle.status}")
        if handle.error:
            lines.append(f"error: {handle.error}")
        lines.append(f"tokens: {handle.tokens}")
        self._phases.update("\n".join(lines))
        self._log.update("\n".join(handle.log_tail))
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from showbible.tui.panes.run_detail import RunDetailPane; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/panes/run_detail.py
git commit -m "feat(tui): add RunDetailPane"
```

---

### Task 21: Wire pane swapping in `ShowBibleApp`

**Files:**
- Modify: `showbible/tui/app.py`

- [ ] **Step 1: Update `ShowBibleApp` to swap panes on sidebar selection**

In `showbible/tui/app.py`:

1. Add imports at the top:

```python
from showbible.tui.panes.arc import ArcPane
from showbible.tui.panes.cast import CastPane
from showbible.tui.panes.lore import LorePane
from showbible.tui.panes.outputs import OutputsPane
from showbible.tui.panes.run_detail import RunDetailPane
```

2. Add the pane registry as a class attribute:

```python
    PANE_FACTORIES = {
        "episodes": EpisodesPane,
        "cast": CastPane,
        "arc": ArcPane,
        "lore": LorePane,
        "outputs": OutputsPane,
    }
```

3. Replace the `compose` content area to use a container the pane can swap into:

```python
    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header-bar")
        with Horizontal(id="main"):
            yield Sidebar()
            with Vertical(id="content"):
                yield EpisodesPane()
        yield Footer()
```

4. Replace `on_sidebar_selection` with a fuller dispatcher:

```python
    def on_sidebar_selection(self, message: SidebarSelection) -> None:
        if message.section == "command":
            self._handle_command(message.key)
            return
        if message.section == "nav":
            factory = self.PANE_FACTORIES.get(message.key)
            if factory is not None:
                self._mount_pane(factory())
            return
        if message.section == "run":
            self._mount_pane(RunDetailPane(message.key))

    def _handle_command(self, key: str) -> None:
        if key == "quit":
            self.exit(0)
        elif key == "snapshot":
            from showbible.tui.screens.snapshot import SnapshotScreen
            self.push_screen(SnapshotScreen())
        elif key == "doctor":
            from showbible.tui.screens.doctor import DoctorScreen
            self.push_screen(DoctorScreen())
        elif key == "run":
            self._dispatch_run()

    def _dispatch_run(self) -> None:
        # Replaced in Task 30 (Run worker).
        self.notify("Run dispatch wired in Task 30.")

    def _mount_pane(self, pane) -> None:
        content = self.query_one("#content", Vertical)
        content.remove_children()
        content.mount(pane)
        pane.refresh_from_state(self.state)
```

- [ ] **Step 2: Run the existing smoke tests**

```bash
python -m pytest tests/test_tui_smoke.py -v
```

Expected: PASS (the existing two tests still work since the default content is still EpisodesPane).

- [ ] **Step 3: Add a Pilot test that selects each navigation item**

Append to `tests/test_tui_smoke.py`:

```python
@pytest.mark.asyncio
async def test_navigate_through_all_panes(tmp_path: Path) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.panes.arc import ArcPane
    from showbible.tui.panes.cast import CastPane
    from showbible.tui.panes.lore import LorePane
    from showbible.tui.panes.outputs import OutputsPane

    vault = init_vault(tmp_path / "demo")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        for key, pane_cls in (("cast", CastPane), ("arc", ArcPane), ("lore", LorePane), ("outputs", OutputsPane)):
            from showbible.tui.widgets.sidebar import SidebarSelection
            app.post_message(SidebarSelection(section="nav", key=key))
            await pilot.pause()
            assert app.query(pane_cls)
```

- [ ] **Step 4: Run the new test**

```bash
python -m pytest tests/test_tui_smoke.py::test_navigate_through_all_panes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add showbible/tui/app.py tests/test_tui_smoke.py
git commit -m "feat(tui): wire sidebar pane swapping"
```

---

## Stage 4 — Modal screens

### Task 22: `ConfirmScreen`

**Files:**
- Create: `showbible/tui/screens/__init__.py`
- Create: `showbible/tui/screens/confirm.py`

- [ ] **Step 1: Create `showbible/tui/screens/__init__.py`**

```python
"""Modal screens for ShowBible."""
```

- [ ] **Step 2: Create `showbible/tui/screens/confirm.py`**

```python
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("escape", "dismiss(False)", "Cancel"),
        Binding("y", "dismiss(True)", "Confirm"),
    ]

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 60;
    }
    ConfirmScreen Label { margin-bottom: 1; }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._prompt)
            yield Button("Cancel", id="cancel")
            yield Button("Confirm", id="confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")
```

- [ ] **Step 3: Smoke import**

```bash
python -c "from showbible.tui.screens.confirm import ConfirmScreen; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add showbible/tui/screens/__init__.py showbible/tui/screens/confirm.py
git commit -m "feat(tui): add ConfirmScreen modal"
```

---

### Task 23: `EntityForm` widget + `AddCastScreen`

**Files:**
- Create: `showbible/tui/widgets/entity_form.py`
- Create: `showbible/tui/screens/add_cast.py`

- [ ] **Step 1: Create `showbible/tui/widgets/entity_form.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select


@dataclass
class FormField:
    name: str
    label: str
    default: str = ""
    options: list[str] | None = None  # if set, render a Select instead of Input


class EntityForm(Vertical):
    DEFAULT_CSS = """
    EntityForm { padding: 1 2; height: auto; }
    EntityForm > Horizontal { height: auto; margin-bottom: 1; }
    EntityForm Label { width: 18; }
    EntityForm Input, EntityForm Select { width: 1fr; }
    EntityForm #form-buttons { align-horizontal: right; }
    """

    def __init__(self, fields: list[FormField], submit_label: str = "Save") -> None:
        super().__init__(id="entity-form")
        self._fields = fields
        self._submit_label = submit_label
        self._inputs: dict[str, Input | Select] = {}

    def compose(self):
        for field in self._fields:
            with Horizontal():
                yield Label(field.label)
                if field.options is not None:
                    widget = Select(
                        [(opt, opt) for opt in field.options],
                        value=field.default or field.options[0],
                        id=f"form-{field.name}",
                    )
                else:
                    widget = Input(value=field.default, id=f"form-{field.name}")
                self._inputs[field.name] = widget
                yield widget
        with Horizontal(id="form-buttons"):
            yield Button("Cancel", id="form-cancel")
            yield Button(self._submit_label, id="form-submit", variant="primary")

    def values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, widget in self._inputs.items():
            if isinstance(widget, Input):
                result[name] = widget.value
            elif isinstance(widget, Select):
                result[name] = "" if widget.value is Select.BLANK else str(widget.value)
        return result
```

- [ ] **Step 2: Create `showbible/tui/screens/add_cast.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from showbible.tui.widgets.entity_form import EntityForm, FormField


@dataclass
class CastFormResult:
    display_name: str
    kind: str
    plays: str
    scope: str  # "show" | "episode"


class AddCastScreen(ModalScreen[CastFormResult | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddCastScreen { align: center middle; }
    AddCastScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 70;
    }
    """

    def __init__(self, *, title: str = "Add cast member", initial: CastFormResult | None = None) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._form = EntityForm(
            [
                FormField("display_name", "Display name", initial.display_name if initial else ""),
                FormField(
                    "kind",
                    "Kind",
                    initial.kind if initial else "actor",
                    options=["actor", "writer", "showrunner", "director"],
                ),
                FormField("plays", "Plays", initial.plays if initial else ""),
                FormField(
                    "scope",
                    "Scope",
                    initial.scope if initial else "show",
                    options=["show", "episode"],
                ),
            ],
        )

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield self._form

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "form-cancel":
            self.dismiss(None)
            return
        if event.button.id == "form-submit":
            values = self._form.values()
            if not values["display_name"].strip():
                self.notify("Display name required.", severity="error")
                return
            self.dismiss(
                CastFormResult(
                    display_name=values["display_name"].strip(),
                    kind=values["kind"].strip() or "actor",
                    plays=values["plays"].strip(),
                    scope=values["scope"].strip() or "show",
                )
            )
```

- [ ] **Step 3: Smoke import**

```bash
python -c "from showbible.tui.screens.add_cast import AddCastScreen, CastFormResult; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add showbible/tui/widgets/entity_form.py showbible/tui/screens/add_cast.py
git commit -m "feat(tui): add EntityForm widget and AddCastScreen modal"
```

---

### Task 24: `AddArcBeatScreen`

**Files:**
- Create: `showbible/tui/screens/add_arc_beat.py`

- [ ] **Step 1: Create `showbible/tui/screens/add_arc_beat.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from showbible.tui.widgets.entity_form import EntityForm, FormField


@dataclass
class ArcBeatFormResult:
    arc_slug: str
    episode_id: str
    status: str
    beat: str


class AddArcBeatScreen(ModalScreen[ArcBeatFormResult | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddArcBeatScreen { align: center middle; }
    AddArcBeatScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 70;
    }
    """

    def __init__(
        self,
        *,
        title: str = "Add arc beat",
        initial: ArcBeatFormResult | None = None,
        default_episode: str = "S01E01",
    ) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._form = EntityForm(
            [
                FormField("arc_slug", "Arc", initial.arc_slug if initial else "season-theme"),
                FormField("episode_id", "Episode", initial.episode_id if initial else default_episode),
                FormField(
                    "status",
                    "Status",
                    initial.status if initial else "planned",
                    options=["planned", "in-progress", "done"],
                ),
                FormField("beat", "Beat", initial.beat if initial else ""),
            ],
        )

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield self._form

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "form-cancel":
            self.dismiss(None)
            return
        if event.button.id == "form-submit":
            values = self._form.values()
            if not values["beat"].strip():
                self.notify("Beat text required.", severity="error")
                return
            self.dismiss(
                ArcBeatFormResult(
                    arc_slug=values["arc_slug"].strip() or "season-theme",
                    episode_id=values["episode_id"].strip() or "S01E01",
                    status=values["status"].strip() or "planned",
                    beat=values["beat"].strip(),
                )
            )
```

- [ ] **Step 2: Commit**

```bash
git add showbible/tui/screens/add_arc_beat.py
git commit -m "feat(tui): add AddArcBeatScreen modal"
```

---

### Task 25: `AddLoreScreen`

**Files:**
- Create: `showbible/tui/screens/add_lore.py`

- [ ] **Step 1: Create `showbible/tui/screens/add_lore.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from showbible.tui.widgets.entity_form import EntityForm, FormField


@dataclass
class LoreFactFormResult:
    text: str
    source: str


class AddLoreScreen(ModalScreen[LoreFactFormResult | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddLoreScreen { align: center middle; }
    AddLoreScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 70;
    }
    """

    def __init__(
        self,
        *,
        title: str = "Add canon fact",
        initial: LoreFactFormResult | None = None,
        default_source: str = "manual",
    ) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._form = EntityForm(
            [
                FormField("text", "Fact", initial.text if initial else ""),
                FormField("source", "Source", initial.source if initial else default_source),
            ],
        )

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield self._form

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "form-cancel":
            self.dismiss(None)
            return
        if event.button.id == "form-submit":
            values = self._form.values()
            if not values["text"].strip():
                self.notify("Fact text required.", severity="error")
                return
            self.dismiss(
                LoreFactFormResult(
                    text=values["text"].strip(),
                    source=values["source"].strip() or "manual",
                )
            )
```

- [ ] **Step 2: Commit**

```bash
git add showbible/tui/screens/add_lore.py
git commit -m "feat(tui): add AddLoreScreen modal"
```

---

### Task 26: `SnapshotScreen` and `DoctorScreen`

**Files:**
- Create: `showbible/tui/screens/snapshot.py`
- Create: `showbible/tui/screens/doctor.py`

- [ ] **Step 1: Create `showbible/tui/screens/snapshot.py`**

```python
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class SnapshotScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
    ]

    DEFAULT_CSS = """
    SnapshotScreen { align: center middle; }
    SnapshotScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 90%;
        height: 80%;
    }
    """

    def compose(self) -> ComposeResult:
        from showbible.cli import _workflow_snapshot_text
        snapshot = _workflow_snapshot_text(
            self.app.state.vault,
            self.app.state.current_episode,
            self.app._provider,
        )
        with Vertical():
            yield Label("Workflow snapshot")
            with VerticalScroll():
                yield Static(snapshot)
            yield Button("Close", id="snapshot-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
```

- [ ] **Step 2: Create `showbible/tui/screens/doctor.py`**

```python
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class DoctorScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
    ]

    DEFAULT_CSS = """
    DoctorScreen { align: center middle; }
    DoctorScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 80%;
        height: 70%;
    }
    """

    def compose(self) -> ComposeResult:
        findings = self.app.state.doctor_findings
        if not findings:
            text = "All clean."
        else:
            text = "\n".join(f"[{f.severity}] {f.path}: {f.message}" for f in findings)
        with Vertical():
            yield Label("Doctor")
            with VerticalScroll():
                yield Static(text)
            yield Button("Close", id="doctor-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
```

- [ ] **Step 3: Smoke import**

```bash
python -c "from showbible.tui.screens.snapshot import SnapshotScreen; from showbible.tui.screens.doctor import DoctorScreen; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add showbible/tui/screens/snapshot.py showbible/tui/screens/doctor.py
git commit -m "feat(tui): add SnapshotScreen and DoctorScreen modals"
```

---

### Task 27: `AISuggestScreen` (LoadingIndicator → SelectionList)

**Files:**
- Create: `showbible/tui/screens/ai_suggest.py`

- [ ] **Step 1: Create `showbible/tui/screens/ai_suggest.py`**

```python
from __future__ import annotations

from typing import Any, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, LoadingIndicator, SelectionList, Static
from textual.widgets.selection_list import Selection
from textual.worker import Worker


class AISuggestScreen(ModalScreen[list[dict] | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AISuggestScreen { align: center middle; }
    AISuggestScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 80%;
        height: 70%;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        generator: Callable[[], list[dict[str, Any]]],
        format_row: Callable[[dict[str, Any]], str],
    ) -> None:
        super().__init__()
        self._title = title
        self._generator = generator
        self._format_row = format_row
        self._loading = LoadingIndicator(id="ai-loading")
        self._status = Static(f"Generating {title}…", id="ai-status")
        self._selection: SelectionList | None = None
        self._error: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="ai-container"):
            yield Label(self._title)
            yield self._status
            yield self._loading

    def on_mount(self) -> None:
        self.run_worker(self._generate, thread=True, exclusive=True)

    def _generate(self) -> list[dict[str, Any]]:
        return self._generator()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.is_finished:
            self._loading.remove()
            if event.worker.error:
                self._status.update(f"Failed: {event.worker.error}")
                container = self.query_one("#ai-container", Vertical)
                container.mount(Button("Close", id="ai-close", variant="primary"))
            else:
                suggestions = event.worker.result or []
                if not suggestions:
                    self._status.update("No suggestions returned.")
                    container = self.query_one("#ai-container", Vertical)
                    container.mount(Button("Close", id="ai-close", variant="primary"))
                    return
                self._status.update("Select suggestions to apply (space toggles, enter applies):")
                self._selection = SelectionList(
                    *(Selection(self._format_row(item), item, initial_state=True) for item in suggestions),
                    id="ai-selection",
                )
                container = self.query_one("#ai-container", Vertical)
                container.mount(self._selection)
                container.mount(Button("Apply", id="ai-apply", variant="primary"))
                container.mount(Button("Cancel", id="ai-cancel"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("ai-cancel", "ai-close"):
            self.dismiss(None)
            return
        if event.button.id == "ai-apply" and self._selection is not None:
            self.dismiss(list(self._selection.selected))
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from showbible.tui.screens.ai_suggest import AISuggestScreen; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/screens/ai_suggest.py
git commit -m "feat(tui): add AISuggestScreen modal"
```

---

## Stage 5 — Behavior wiring

### Task 28: Wire CastPane → modals → vault helpers

**Files:**
- Modify: `showbible/tui/app.py`

- [ ] **Step 1: Add a CastAction handler in `ShowBibleApp`**

In `showbible/tui/app.py`, add the import:

```python
from showbible.tui.panes.cast import CastAction
from showbible.tui.screens.add_cast import AddCastScreen, CastFormResult
from showbible.tui.screens.confirm import ConfirmScreen
from showbible.tui.screens.ai_suggest import AISuggestScreen
```

Add the handler:

```python
    def on_cast_action(self, message: CastAction) -> None:
        from showbible.vault import (
            CastRole,
            add_cast_role,
            add_episode_cast_role,
            people,
            remove_cast_role,
            remove_episode_cast_role,
            slugify,
            write_person,
        )

        vault = self.state.vault
        episode_id = self.state.current_episode

        if message.action == "add":
            self.push_screen(
                AddCastScreen(),
                lambda result: self._apply_cast_form(result),
            )
        elif message.action == "edit" and message.person_slug:
            existing = next((r for r in self.state.cast if r.person == message.person_slug), None)
            if existing is None:
                return
            people_by_slug = {p["slug"]: p for p in people(vault)}
            display = people_by_slug.get(existing.person, {}).get("display_name", existing.person)
            self.push_screen(
                AddCastScreen(
                    title="Edit cast member",
                    initial=CastFormResult(
                        display_name=display,
                        kind=existing.kind,
                        plays=existing.plays or "",
                        scope="show",
                    ),
                ),
                lambda result: self._apply_cast_form(result, replacing=existing.person),
            )
        elif message.action == "delete" and message.person_slug:
            self.push_screen(
                ConfirmScreen(f"Delete {message.person_slug}?"),
                lambda confirmed: self._delete_cast_role(message.person_slug, confirmed or False),
            )
        elif message.action == "suggest":
            from showbible.cli import _generate_cast_suggestions, _apply_cast_suggestions
            self.push_screen(
                AISuggestScreen(
                    title="cast suggestions",
                    generator=lambda: _generate_cast_suggestions(vault, episode_id, self._provider, limit=6),
                    format_row=lambda item: f"{item.get('kind', 'actor')}: {item.get('person')} ({item.get('display_name', '')})",
                ),
                lambda picked: self._apply_cast_picked(picked),
            )

    def _apply_cast_form(self, result: CastFormResult | None, *, replacing: str | None = None) -> None:
        if result is None:
            return
        from showbible.vault import (
            CastRole,
            add_cast_role,
            add_episode_cast_role,
            remove_cast_role,
            remove_episode_cast_role,
            slugify,
            write_person,
        )
        slug = slugify(result.display_name)
        write_person(self.state.vault, slug, result.display_name, result.kind, result.plays or None)
        if replacing and replacing != slug:
            remove_cast_role(self.state.vault, replacing)
            remove_episode_cast_role(self.state.vault, self.state.current_episode, replacing)
        role = CastRole(kind=result.kind, person=slug, plays=result.plays or None)
        if result.scope == "episode":
            add_episode_cast_role(self.state.vault, self.state.current_episode, role)
            msg = f"Added {result.kind} {result.display_name} to {self.state.current_episode}."
        else:
            add_cast_role(self.state.vault, role)
            msg = f"Added show {result.kind} {result.display_name}."
        self.state = self.state.with_action(msg).refreshed_from_disk()
        self._populate_panes()

    def _delete_cast_role(self, person_slug: str, confirmed: bool) -> None:
        if not confirmed:
            return
        from showbible.vault import remove_cast_role, remove_episode_cast_role
        remove_cast_role(self.state.vault, person_slug)
        remove_episode_cast_role(self.state.vault, self.state.current_episode, person_slug)
        self.state = self.state.with_action(f"Deleted {person_slug}.").refreshed_from_disk()
        self._populate_panes()

    def _apply_cast_picked(self, picked: list[dict] | None) -> None:
        if not picked:
            return
        from showbible.cli import _apply_cast_suggestions
        _apply_cast_suggestions(self.state.vault, self.state.current_episode, picked)
        self.state = self.state.with_action(f"Applied {len(picked)} cast suggestion(s).").refreshed_from_disk()
        self._populate_panes()
```

- [ ] **Step 2: Smoke check**

```bash
python -c "import showbible.tui.app; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/app.py
git commit -m "feat(tui): wire CastPane add/edit/delete/suggest"
```

---

### Task 29: Wire ArcPane and LorePane

**Files:**
- Modify: `showbible/tui/app.py`

- [ ] **Step 1: Add ArcAction and LoreAction handlers**

In `showbible/tui/app.py`, add imports:

```python
from showbible.tui.panes.arc import ArcAction
from showbible.tui.panes.lore import LoreAction
from showbible.tui.screens.add_arc_beat import AddArcBeatScreen, ArcBeatFormResult
from showbible.tui.screens.add_lore import AddLoreScreen, LoreFactFormResult
```

Add the handlers:

```python
    def on_arc_action(self, message: ArcAction) -> None:
        from showbible.vault import add_arc_beat, remove_arc_beat, update_arc_beat

        if message.action == "add":
            self.push_screen(
                AddArcBeatScreen(default_episode=self.state.current_episode),
                lambda result: self._apply_arc_form(result),
            )
        elif message.action == "edit" and message.arc_slug and message.beat:
            self.push_screen(
                AddArcBeatScreen(
                    title="Edit arc beat",
                    initial=ArcBeatFormResult(
                        arc_slug=message.arc_slug,
                        episode_id=message.episode_id or self.state.current_episode,
                        status="planned",
                        beat=message.beat,
                    ),
                ),
                lambda result: self._apply_arc_form(result, original=(message.arc_slug, message.episode_id, message.beat)),
            )
        elif message.action == "delete" and message.arc_slug and message.beat:
            self.push_screen(
                ConfirmScreen(f"Delete beat '{message.beat[:40]}'?"),
                lambda ok: self._delete_arc_beat(message.arc_slug, message.episode_id, message.beat, ok or False),
            )
        elif message.action == "suggest":
            from showbible.cli import _generate_arc_suggestions, _apply_arc_suggestions
            slug = message.arc_slug or "season-theme"
            self.push_screen(
                AISuggestScreen(
                    title=f"arc beat suggestions for {slug}",
                    generator=lambda: _generate_arc_suggestions(self.state.vault, self.state.current_episode, self._provider, arc_slug=slug),
                    format_row=lambda item: f"{item.get('episode')} [{item.get('status')}] {item.get('beat')}",
                ),
                lambda picked: self._apply_arc_picked(slug, picked),
            )

    def _apply_arc_form(self, result: ArcBeatFormResult | None, *, original: tuple | None = None) -> None:
        if result is None:
            return
        from showbible.vault import add_arc_beat, update_arc_beat
        if original:
            arc_slug, episode_id, beat = original
            update_arc_beat(
                self.state.vault,
                arc_slug=arc_slug,
                episode_id=episode_id,
                original_beat=beat,
                new_episode_id=result.episode_id,
                new_status=result.status,
                new_beat=result.beat,
            )
            msg = f"Updated beat in {arc_slug}."
        else:
            add_arc_beat(self.state.vault, result.arc_slug, result.episode_id, result.status, result.beat)
            msg = f"Added beat to {result.arc_slug}: {result.episode_id} [{result.status}] {result.beat}"
        self.state = self.state.with_action(msg).refreshed_from_disk()
        self._populate_panes()

    def _delete_arc_beat(self, arc_slug: str, episode_id: str | None, beat: str, confirmed: bool) -> None:
        if not confirmed:
            return
        from showbible.vault import remove_arc_beat
        remove_arc_beat(self.state.vault, arc_slug, episode_id or self.state.current_episode, beat)
        self.state = self.state.with_action(f"Deleted beat from {arc_slug}.").refreshed_from_disk()
        self._populate_panes()

    def _apply_arc_picked(self, arc_slug: str, picked: list[dict] | None) -> None:
        if not picked:
            return
        from showbible.cli import _apply_arc_suggestions
        _apply_arc_suggestions(self.state.vault, arc_slug, picked)
        self.state = self.state.with_action(f"Applied {len(picked)} arc beat suggestion(s) to {arc_slug}.").refreshed_from_disk()
        self._populate_panes()

    def on_lore_action(self, message: LoreAction) -> None:
        if message.action == "add":
            self.push_screen(
                AddLoreScreen(default_source=self.state.current_episode or "manual"),
                lambda result: self._apply_lore_form(result),
            )
        elif message.action == "edit" and message.fact_text:
            existing = next((f for f in self.state.lore_facts if f.text == message.fact_text), None)
            if existing is None:
                return
            self.push_screen(
                AddLoreScreen(
                    title="Edit canon fact",
                    initial=LoreFactFormResult(text=existing.text, source=existing.source),
                ),
                lambda result: self._apply_lore_form(result, original=existing.text),
            )
        elif message.action == "delete" and message.fact_text:
            self.push_screen(
                ConfirmScreen(f"Delete '{message.fact_text[:40]}'?"),
                lambda ok: self._delete_lore_fact(message.fact_text, ok or False),
            )
        elif message.action == "suggest":
            from showbible.cli import _generate_lore_suggestions, _apply_lore_suggestions
            self.push_screen(
                AISuggestScreen(
                    title="canon fact suggestions",
                    generator=lambda: _generate_lore_suggestions(self.state.vault, self.state.current_episode, self._provider),
                    format_row=lambda item: str(item.get("fact", "")),
                ),
                lambda picked: self._apply_lore_picked(picked),
            )

    def _apply_lore_form(self, result: LoreFactFormResult | None, *, original: str | None = None) -> None:
        if result is None:
            return
        from showbible.vault import add_lore_fact, update_lore_fact
        if original:
            update_lore_fact(self.state.vault, original_text=original, new_text=result.text, new_source=result.source)
            msg = "Updated fact."
        else:
            add_lore_fact(self.state.vault, result.text, source=result.source)
            msg = f"Added fact (source {result.source})."
        self.state = self.state.with_action(msg).refreshed_from_disk()
        self._populate_panes()

    def _delete_lore_fact(self, text: str, confirmed: bool) -> None:
        if not confirmed:
            return
        from showbible.vault import remove_lore_fact
        remove_lore_fact(self.state.vault, text)
        self.state = self.state.with_action("Deleted fact.").refreshed_from_disk()
        self._populate_panes()

    def _apply_lore_picked(self, picked: list[dict] | None) -> None:
        if not picked:
            return
        from showbible.cli import _apply_lore_suggestions
        _apply_lore_suggestions(self.state.vault, picked, source=self.state.current_episode or "manual")
        self.state = self.state.with_action(f"Applied {len(picked)} lore fact suggestion(s).").refreshed_from_disk()
        self._populate_panes()
```

- [ ] **Step 2: Smoke check**

```bash
python -c "import showbible.tui.app; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add showbible/tui/app.py
git commit -m "feat(tui): wire ArcPane and LorePane add/edit/delete/suggest"
```

---

### Task 30: Wire Run worker (concurrent, backgrounded)

**Files:**
- Modify: `showbible/tui/app.py`

- [ ] **Step 1: Replace `_dispatch_run`**

In `showbible/tui/app.py`, replace `_dispatch_run` with:

```python
    def _dispatch_run(self) -> None:
        episode_id = self.state.current_episode
        handle = self._registry.start(episode_id)
        run_id = handle.run_id
        self.state = self.state.with_runs(self._registry.snapshot())
        self._update_chrome()
        self.run_worker(
            lambda: self._run_episode(run_id, episode_id),
            thread=True,
            name=f"run-{run_id}",
            group="runs",
            exclusive=False,
        )

    def _run_episode(self, run_id: str, episode_id: str) -> None:
        from showbible.engine import run_episode

        def progress(event: str, phase: str, payload: dict) -> None:
            self.call_from_thread(self._registry.on_progress, run_id, event, phase, payload)
            self.call_from_thread(self._propagate_runs)

        try:
            result = run_episode(self.state.vault, episode_id, self._provider, progress=progress)
            message = (
                f"Ran {result.episode_id}: {len(result.completed_phases)} phase(s), "
                f"{len(result.skipped_phases)} skipped, {result.tokens} token(s)."
            )
            self.call_from_thread(self._registry.on_completed, run_id, message=message)
            self.call_from_thread(self.notify, message)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._registry.on_failed, run_id, error=str(exc))
            self.call_from_thread(self.notify, f"{episode_id} failed: {exc}", severity="error")
        finally:
            self.call_from_thread(self._propagate_runs)

    def _propagate_runs(self) -> None:
        self.state = self.state.with_runs(self._registry.snapshot())
        self._update_chrome()
        self._populate_panes()
```

- [ ] **Step 2: Add a Pilot test that runs an episode with the mock provider**

Append to `tests/test_tui_smoke.py`:

```python
@pytest.mark.asyncio
async def test_run_episode_with_mock_provider(tmp_path: Path) -> None:
    import asyncio

    from showbible.tui.app import ShowBibleApp
    from showbible.tui.widgets.sidebar import SidebarSelection

    vault = init_vault(tmp_path / "demo")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.post_message(SidebarSelection(section="command", key="run"))
        await pilot.pause()
        # wait until the worker finishes (mock provider is fast)
        for _ in range(50):
            if app.state.runs:
                handle = next(iter(app.state.runs.values()))
                if handle.status in {"complete", "failed"}:
                    break
            await asyncio.sleep(0.1)
        assert app.state.runs
        handle = next(iter(app.state.runs.values()))
        assert handle.status == "complete", handle.error
```

- [ ] **Step 3: Run the test**

```bash
python -m pytest tests/test_tui_smoke.py::test_run_episode_with_mock_provider -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add showbible/tui/app.py tests/test_tui_smoke.py
git commit -m "feat(tui): dispatch concurrent Run workers with progress bridge"
```

---

## Stage 6 — Final verification

### Task 31: Pilot smoke for AI suggest path

**Files:**
- Modify: `tests/test_tui_smoke.py`

- [ ] **Step 1: Add the Pilot test**

Append to `tests/test_tui_smoke.py`:

```python
@pytest.mark.asyncio
async def test_arc_suggest_modal_with_stub_provider(tmp_path: Path, monkeypatch) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.panes.arc import ArcAction

    vault = init_vault(tmp_path / "demo")

    class Provider:
        name = "stub"

        def generate(self, phase, episode_id, prompt):
            return type(
                "Generation",
                (),
                {
                    "text": '[{"episode":"S01E01","status":"planned","beat":"raise the stakes"}]',
                    "tokens": 0,
                    "dollars": 0.0,
                },
            )()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="stub")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.post_message(ArcAction(action="suggest", arc_slug="season-theme"))
        await pilot.pause()
        # AISuggestScreen mounts; let the worker finish
        import asyncio
        for _ in range(30):
            await asyncio.sleep(0.1)
            from showbible.tui.screens.ai_suggest import AISuggestScreen
            if app.screen.__class__ is AISuggestScreen:
                if app.screen.query("SelectionList"):
                    break
        from showbible.tui.screens.ai_suggest import AISuggestScreen
        assert isinstance(app.screen, AISuggestScreen)
        assert app.screen.query("SelectionList")
```

- [ ] **Step 2: Run**

```bash
python -m pytest tests/test_tui_smoke.py::test_arc_suggest_modal_with_stub_provider -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tui_smoke.py
git commit -m "test(tui): add Pilot smoke for AI suggest modal"
```

---

### Task 32: End-to-end verification

**Files:** none modified.

- [ ] **Step 1: Full test suite**

```bash
python -m pytest -q
```

Expected: all green; ~6 Pilot tests + the existing unit tests.

- [ ] **Step 2: CLI surface check**

```bash
python -m showbible --help > /dev/null
python -m showbible tui --help > /dev/null
python -m showbible arcs suggest --help > /dev/null
python -m showbible lore suggest --help > /dev/null
```

Expected: each exits 0 with no traceback.

- [ ] **Step 3: Manual TUI smoke (interactive — only run if a real terminal is available)**

```bash
mkdir -p /tmp/showbible-textual-smoke && rm -rf /tmp/showbible-textual-smoke/demo
python -m showbible init --vault /tmp/showbible-textual-smoke/demo --show "Smoke Show"
python -m showbible tui --vault /tmp/showbible-textual-smoke/demo --episode S01E01 --provider mock
```

Manually verify:
- Sidebar shows NAVIGATE (Episodes/Cast/Arc/Lore/Outputs) and COMMAND (Run/Snapshot/Doctor/Quit) sections.
- Selecting each NAVIGATE row swaps the content pane to the right widget.
- Pressing `a` in Cast/Arc/Lore opens the corresponding modal; submitting it adds a row to the list within ~1 second.
- Pressing `s` in Cast/Arc/Lore opens the AI suggest modal with a spinner, then a selection list; applying picks adds the corresponding rows.
- Selecting Run in COMMAND triggers a background run; the Active Runs sidebar section shows a `● S01E01` row that disappears once complete; a footer toast announces completion.
- Snapshot and Doctor selections open their modals; Esc dismisses.
- Quit exits the app cleanly.

If everything passes, no commit is needed. If any item fails, file follow-up issues rather than patching this plan in place.

---

## Non-goals (explicitly out of scope, do not implement)

- WebSocket/NATS/Redis transports (Phase 3/4).
- Async-aware engine + run cancellation tokens (Phase 1 prerequisite).
- Updates to `showbible/server.py` or `showbible/ui/index.html`.
- Token-level streaming during phases.
- Custom CSS theming beyond the snippets shown.
- Multi-vault switching inside the app.
