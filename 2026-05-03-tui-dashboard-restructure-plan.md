# TUI Dashboard Restructure Implementation Plan

> **Superseded.** This plan was built on the curses-based design at [2026-05-03-tui-dashboard-restructure-design.md](2026-05-03-tui-dashboard-restructure-design.md), which has been replaced by the Textual rewrite at [2026-05-03-textual-tui-design.md](2026-05-03-textual-tui-design.md). Tasks 0 and 1 have already shipped (`pytest` dev-dep, dashboard sub-screen routing commit, and `arc_beats` reader). The remaining curses-specific tasks (9–12) are abandoned. The framework-neutral pieces (Tasks 2–8: arc/lore vault mutators and AI suggest CLIs) are absorbed into the new spec and will be re-planned there.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the `showbible tui` dashboard menu into NAVIGATE (Episodes/Cast/Arc/Lore/Outputs) and COMMAND (Run/Snapshot/Doctor/Quit) sections, and bring Arc and Lore to feature parity with Cast via dedicated two-pane sub-screens with add/edit/delete/AI-suggest.

**Architecture:** Dashboard menu becomes two labelled sections separated by a blank row. Arc and Lore each get a `_arc_tui` / `_lore_tui` sub-screen modelled after `_cast_tui`. Vault gains library helpers (`arc_beats`, `add_arc_beat`, …, `lore_facts`, `add_lore_fact`, …) so the TUI calls Python functions instead of shelling argparse. Two new CLI commands `arcs suggest` / `lore suggest` mirror `cmd_cast_suggest` and back the new `s` hotkey.

**Tech Stack:** Python 3.11+, stdlib `curses`, `argparse`, `pytest`. No new dependencies.

**Spec:** `2026-05-03-tui-dashboard-restructure-design.md`

---

## Pre-work — Baseline

### Task 0: Verify and stabilise the existing test suite

The current uncommitted edit in `showbible/cli.py` already removed action branches (`episode-select`, `cast-show-add`, `cast-episode-add`, `suggest-show-apply`, `outputs`) from `_run_dashboard_action`, but `tests/test_showbible.py::test_dashboard_actions_construct_show_without_leaving_workflow` still calls those actions. Confirm what the suite reports today and decide whether to fix the test now or replace it as part of Task 8 (menu restructure).

**Files:**
- Read: `tests/test_showbible.py:239-323`
- Read: `showbible/cli.py:920-960` (the trimmed `_run_dashboard_action`)

- [ ] **Step 1: Run the suite and capture failures**

```bash
cd /Users/eric/code/showbible.io
python -m pytest tests/test_showbible.py -x 2>&1 | tail -40
```

Expected: at least `test_dashboard_actions_construct_show_without_leaving_workflow` fails because actions like `"episode-select"` no longer exist. Note any other failures — they must be triaged before later tasks.

- [ ] **Step 2: Stage the existing dashboard restructure changes (so the working tree is clean for the new work)**

```bash
git add showbible/cli.py
git commit -m "refactor: route episodes/cast/outputs through sub-screens"
```

- [ ] **Step 3: Replace the obsolete dashboard test with a thin equivalent**

Edit `tests/test_showbible.py:239-323` and replace the entire `test_dashboard_actions_construct_show_without_leaving_workflow` body with one that covers the actions still handled by `_run_dashboard_action` (snapshot, arc-add, lore-add, run, doctor):

```python
def test_dashboard_actions_construct_show_without_leaving_workflow(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    episode_id = "S01E01"

    episode_id, message = _run_dashboard_action(vault, episode_id, "snapshot", "mock")
    assert "ShowBible workflow for S01E01" in message

    values = iter(["The pilot pays off a hidden debt."])
    episode_id, message = _run_dashboard_action(
        vault,
        episode_id,
        "arc-add",
        "mock",
        prompt=lambda label, default="": next(values),
    )
    assert "Added arc beat" in message
    assert "S01E01 [planned] The pilot pays off" in (vault / "arcs" / "season-theme.md").read_text(encoding="utf-8")

    values = iter(["The protagonist already knows the secret."])
    episode_id, message = _run_dashboard_action(
        vault,
        episode_id,
        "lore-add",
        "mock",
        prompt=lambda label, default="": next(values),
    )
    assert "Added lore fact" in message
    assert "already knows the secret" in (vault / "lore-bible" / "canon.md").read_text(encoding="utf-8")

    episode_id, message = _run_dashboard_action(vault, episode_id, "run", "mock")
    assert "Ran S01E01" in message
    assert read_json(vault / "episodes" / "S01E01" / "meta.json", {})["status"] == "done"

    episode_id, message = _run_dashboard_action(vault, episode_id, "doctor", "mock")
    assert message == "Doctor clean."
```

- [ ] **Step 4: Run the suite again, expect green**

```bash
python -m pytest tests/test_showbible.py -x 2>&1 | tail -20
```

Expected: all tests pass (or at least no regressions vs. the documented baseline).

- [ ] **Step 5: Commit**

```bash
git add tests/test_showbible.py
git commit -m "test: align dashboard test with sub-screen routing"
```

---

## Stage 1 — Vault helpers (Arc)

### Task 1: `arc_beats(vault)` reader

**Files:**
- Modify: `showbible/vault.py` (add near other arc-related code; if none, append at end before final blank line)
- Test: `tests/test_showbible.py` (append at end)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_showbible.py`:

```python
def test_arc_beats_reads_all_arcs(tmp_path: Path) -> None:
    from showbible.vault import arc_beats

    vault = init_vault(tmp_path / "demo")
    atomic_write_text(
        vault / "arcs" / "season-theme.md",
        "# Season Theme\n\n## Episode Beats\n\n- S01E01 [planned] open the season\n- S01E02 [done] turn the screw\n",
    )
    atomic_write_text(
        vault / "arcs" / "ensemble.md",
        "# Ensemble\n\n## Episode Beats\n\n- S01E01 [planned] introduce the rival\n",
    )

    beats = arc_beats(vault)

    assert [(b.arc, b.episode, b.status, b.beat) for b in beats] == [
        ("ensemble", "S01E01", "planned", "introduce the rival"),
        ("season-theme", "S01E01", "planned", "open the season"),
        ("season-theme", "S01E02", "done", "turn the screw"),
    ]
    assert beats[0].file == vault / "arcs" / "ensemble.md"
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python -m pytest tests/test_showbible.py::test_arc_beats_reads_all_arcs -v
```

Expected: `ImportError: cannot import name 'arc_beats' from 'showbible.vault'`.

- [ ] **Step 3: Implement the helper in `showbible/vault.py`**

Add near the existing dataclasses (after `CastRole`):

```python
@dataclass(frozen=True)
class ArcBeat:
    arc: str
    episode: str
    status: str
    beat: str
    file: Path
```

Add this function (place it near `doctor()` or wherever other arc-aware code lives):

```python
def arc_beats(vault: Path) -> list[ArcBeat]:
    arcs_dir = vault / "arcs"
    if not arcs_dir.is_dir():
        return []
    pattern = re.compile(r"^-\s*(S\d+E\d+)\s+\[([^\]]+)\]\s+(.+)$", flags=re.IGNORECASE)
    results: list[ArcBeat] = []
    for path in sorted(arcs_dir.glob("*.md")):
        slug = path.stem
        for raw in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(raw.strip())
            if match:
                results.append(
                    ArcBeat(
                        arc=slug,
                        episode=match.group(1).upper(),
                        status=match.group(2).strip(),
                        beat=match.group(3).strip(),
                        file=path,
                    )
                )
    return results
```

If `re` is not already imported at the top of `vault.py`, add `import re` to the existing imports.

- [ ] **Step 4: Run the test, expect pass**

```bash
python -m pytest tests/test_showbible.py::test_arc_beats_reads_all_arcs -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add showbible/vault.py tests/test_showbible.py
git commit -m "feat(vault): add arc_beats reader"
```

---

### Task 2: `add_arc_beat`, `update_arc_beat`, `remove_arc_beat`

**Files:**
- Modify: `showbible/vault.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing tests**

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

Expected: ImportError naming `add_arc_beat`.

- [ ] **Step 3: Implement the helpers in `showbible/vault.py`**

Add to `vault.py`:

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
    target = _arc_line(episode_id, _current_status(path, episode_id, original_beat), original_beat)
    replacement = _arc_line(new_episode_id, new_status, new_beat)
    text = path.read_text(encoding="utf-8")
    new_text, count = _replace_arc_line(text, episode_id, original_beat, replacement)
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


def _current_status(path: Path, episode_id: str, beat: str) -> str:
    pattern = re.compile(
        rf"^-\s*{re.escape(episode_id.upper())}\s+\[([^\]]+)\]\s+{re.escape(beat.strip())}\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else "planned"


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

- [ ] **Step 4: Run the test, expect pass**

```bash
python -m pytest tests/test_showbible.py::test_arc_beat_round_trip -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add showbible/vault.py tests/test_showbible.py
git commit -m "feat(vault): add/update/remove_arc_beat helpers"
```

---

### Task 3: Refactor `cmd_arcs_add` to use the helper

**Files:**
- Modify: `showbible/cli.py:584-597`

- [ ] **Step 1: Confirm the existing CLI test stays green pre-refactor**

```bash
python -m pytest tests/test_showbible.py::test_arcs_follow_current_episode_folder -v
```

Expected: PASS (baseline).

- [ ] **Step 2: Replace the body of `cmd_arcs_add`**

Edit `showbible/cli.py:584-597` to:

```python
def cmd_arcs_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _arc_episode_scope(vault, args) or "S01E01"
    path = add_arc_beat(vault, args.arc, episode_id, args.status, args.beat)
    print(f"Added arc beat to {path.name}: {episode_id} [{args.status}] {args.beat.strip()}")
    return 0
```

Add `add_arc_beat` to the existing `from showbible.vault import …` statement in `cli.py`.

- [ ] **Step 3: Run the same CLI test, expect identical output**

```bash
python -m pytest tests/test_showbible.py::test_arcs_follow_current_episode_folder -v
```

Expected: PASS.

- [ ] **Step 4: Run full suite to be safe**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add showbible/cli.py
git commit -m "refactor(cli): cmd_arcs_add uses add_arc_beat helper"
```

---

## Stage 2 — Vault helpers (Lore)

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

- [ ] **Step 2: Run the test, expect ImportError**

```bash
python -m pytest tests/test_showbible.py::test_lore_facts_parses_canon -v
```

Expected: ImportError.

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

- [ ] **Step 4: Run the test, expect pass**

```bash
python -m pytest tests/test_showbible.py::test_lore_facts_parses_canon -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add showbible/vault.py tests/test_showbible.py
git commit -m "feat(vault): add lore_facts reader"
```

---

### Task 5: `add_lore_fact`, `update_lore_fact`, `remove_lore_fact`

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

- [ ] **Step 3: Implement the helpers in `showbible/vault.py`**

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

Add `add_lore_fact` to the `from showbible.vault import …` line in `cli.py`.

- [ ] **Step 2: Run the lore-touching test from `test_episode_and_cast_commands` plus the dashboard test**

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

## Stage 3 — AI suggestion commands

### Task 6.5: Generalise the suggestion picker

The cast picker is hard-coded to cast suggestion shape (`kind`, `person`, `display_name`, `plays`). Extract a generic version so arc/lore suggest commands can reuse it for `--pick`.

**Files:**
- Modify: `showbible/cli.py:1417-1463` (`_pick_cast_suggestions`)
- Test: `tests/test_showbible.py` (only if a non-curses-driven test fits — otherwise rely on existing cast-picker behaviour staying correct via the unchanged `cmd_cast_suggest` path)

- [ ] **Step 1: Add the generic helper alongside the existing picker**

Insert this function immediately above `_pick_cast_suggestions` in `cli.py`:

```python
def _pick_suggestions(
    suggestions: list[dict[str, object]],
    title: str,
    format_row: Callable[[dict[str, object]], str],
) -> list[dict[str, object]]:
    if not suggestions:
        return []
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(json.dumps(suggestions, indent=2))
        print("No interactive terminal detected; rerun with --apply to accept all suggestions.")
        return []
    selected: set[int] = set()
    current = 0

    def draw(screen: "curses.window") -> None:
        nonlocal current, selected
        curses.curs_set(0)
        screen.keypad(True)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(0, 0, f"ShowBible - {title}", width - 1, curses.A_BOLD)
            screen.addnstr(1, 0, "space select  enter apply  a all  q cancel", width - 1)
            for index, item in enumerate(suggestions[: max(0, height - 4)]):
                marker = "[x]" if index in selected else "[ ]"
                line = f"{marker} {format_row(item)}"
                attr = curses.A_REVERSE if index == current else curses.A_NORMAL
                screen.addnstr(index + 3, 0, line, width - 1, attr)
            key = screen.getch()
            if key in (ord("q"), 27):
                selected.clear()
                return
            if key in (curses.KEY_DOWN, ord("j")):
                current = min(len(suggestions) - 1, current + 1)
            elif key in (curses.KEY_UP, ord("k")):
                current = max(0, current - 1)
            elif key == ord(" "):
                if current in selected:
                    selected.remove(current)
                else:
                    selected.add(current)
            elif key == ord("a"):
                selected = set(range(len(suggestions)))
            elif key in (curses.KEY_ENTER, 10, 13):
                if not selected:
                    selected.add(current)
                return

    curses.wrapper(draw)
    return [suggestions[index] for index in sorted(selected)]
```

If `Callable` isn't already imported, add it: `from typing import Callable`.

- [ ] **Step 2: Reduce `_pick_cast_suggestions` to a thin wrapper**

Replace the existing body of `_pick_cast_suggestions` with:

```python
def _pick_cast_suggestions(suggestions: list[dict[str, object]], title: str) -> list[dict[str, object]]:
    def format_row(item: dict[str, object]) -> str:
        plays = f" as {item.get('plays')}" if item.get("plays") else ""
        return f"{item.get('kind', 'actor')}: {item.get('person')} ({item.get('display_name', '')}){plays}"

    return _pick_suggestions(suggestions, title, format_row)
```

- [ ] **Step 3: Run the cast suite to confirm no behaviour change**

```bash
python -m pytest tests/test_showbible.py -k "cast" 2>&1 | tail -10
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add showbible/cli.py
git commit -m "refactor(cli): extract _pick_suggestions generic picker"
```

---

### Task 7: `_generate_arc_suggestions` + `arcs suggest` CLI

Mirrors `_generate_cast_suggestions` / `cmd_cast_suggest`. The model returns a JSON array of `{episode, status, beat}` objects; on `ProviderError` we fall back to a small static seed.

**Files:**
- Modify: `showbible/cli.py` (add functions next to the cast equivalents around line 1248; add subparser entry next to `arcs_add` around line 302)
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write a happy-path test with a stub provider**

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
    assert (vault / "arcs" / "season-theme.md").exists()
```

- [ ] **Step 2: Write a provider-failure fallback test**

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

- [ ] **Step 3: Run both tests, expect failure**

```bash
python -m pytest tests/test_showbible.py::test_arcs_suggest_applies_with_stub_provider tests/test_showbible.py::test_arcs_suggest_falls_back_when_provider_fails -v
```

Expected: usage error from argparse — `arcs suggest` is not a subcommand yet.

- [ ] **Step 4: Add the subparser entry in `build_parser`**

Find the block defining the `arcs` subparser (around `cli.py:286-308`). Immediately after the `arcs_add.set_defaults(func=cmd_arcs_add)` line, add:

```python
    arcs_suggest = arcs_sub.add_parser("suggest", help="suggest arc beats with the AI provider")
    add_vault_flag(arcs_suggest)
    arcs_suggest.add_argument("--episode", help="episode scope; defaults from cwd or room state")
    arcs_suggest.add_argument("--arc", default="season-theme")
    arcs_suggest.add_argument("--provider", default=DEFAULT_PROVIDER)
    arcs_suggest.add_argument("--limit", type=int, default=6)
    arcs_suggest.add_argument("--apply", action="store_true")
    arcs_suggest.add_argument("--pick", action="store_true")
    arcs_suggest.add_argument("--json", action="store_true")
    arcs_suggest.set_defaults(func=cmd_arcs_suggest)
```

(`DEFAULT_PROVIDER` is already used by the cast suggest parser — reuse that symbol.)

- [ ] **Step 5: Implement `_generate_arc_suggestions` and `cmd_arcs_suggest`**

Add to `cli.py` near the cast equivalents:

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
    elif args.pick or _should_pick(args):
        picked = _pick_suggestions(
            suggestions,
            f"{args.arc} arc suggestions",
            lambda item: f"{item.get('episode')} [{item.get('status')}] {item.get('beat')}",
        )
        if picked:
            applied = _apply_arc_suggestions(vault, args.arc, picked)
            print(f"Applied {applied} selected arc beat suggestion(s) to {args.arc}.")
        else:
            print("No arc suggestions applied.")
    elif args.json:
        print(json.dumps(suggestions, indent=2, sort_keys=True))
    else:
        print(json.dumps(suggestions, indent=2))
    return 0
```

Add `arc_beats` and `add_arc_beat` to the existing `from showbible.vault import …` statement if not already imported.

- [ ] **Step 6: Run the new tests, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_arcs_suggest_applies_with_stub_provider tests/test_showbible.py::test_arcs_suggest_falls_back_when_provider_fails -v
```

- [ ] **Step 7: Run the full suite to catch regressions**

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

Same shape as Task 7 but for facts.

**Files:**
- Modify: `showbible/cli.py`
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the happy-path and fallback tests**

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

- [ ] **Step 2: Run, expect failure (no subcommand)**

```bash
python -m pytest tests/test_showbible.py::test_lore_suggest_applies_with_stub_provider tests/test_showbible.py::test_lore_suggest_falls_back_when_provider_fails -v
```

- [ ] **Step 3: Add the subparser entry**

After the existing `lore_paths.set_defaults(func=cmd_lore_paths)` line in `build_parser`, add:

```python
    lore_suggest = lore_sub.add_parser("suggest", help="suggest canon facts with the AI provider")
    add_vault_flag(lore_suggest)
    lore_suggest.add_argument("--episode", help="episode scope; defaults from cwd or room state")
    lore_suggest.add_argument("--provider", default=DEFAULT_PROVIDER)
    lore_suggest.add_argument("--limit", type=int, default=6)
    lore_suggest.add_argument("--apply", action="store_true")
    lore_suggest.add_argument("--pick", action="store_true")
    lore_suggest.add_argument("--json", action="store_true")
    lore_suggest.set_defaults(func=cmd_lore_suggest)
```

- [ ] **Step 4: Implement `_generate_lore_suggestions` and `cmd_lore_suggest`**

Add to `cli.py` near the lore command code:

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
    elif args.pick or _should_pick(args):
        picked = _pick_suggestions(
            suggestions,
            "lore fact suggestions",
            lambda item: str(item.get("fact", "")),
        )
        if picked:
            applied = _apply_lore_suggestions(vault, picked, source=episode_id or "manual")
            print(f"Applied {applied} selected lore fact suggestion(s).")
        else:
            print("No lore suggestions applied.")
    elif args.json:
        print(json.dumps(suggestions, indent=2, sort_keys=True))
    else:
        print(json.dumps(suggestions, indent=2))
    return 0
```

Add `lore_facts` and `add_lore_fact` to the `from showbible.vault import …` line if missing.

- [ ] **Step 5: Run the new tests, expect PASS**

```bash
python -m pytest tests/test_showbible.py::test_lore_suggest_applies_with_stub_provider tests/test_showbible.py::test_lore_suggest_falls_back_when_provider_fails -v
```

- [ ] **Step 6: Full suite check**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

- [ ] **Step 7: Commit**

```bash
git add showbible/cli.py tests/test_showbible.py
git commit -m "feat(cli): add 'lore suggest' AI command"
```

---

## Stage 4 — Dashboard menu restructure

### Task 9: Split dashboard menu into NAVIGATE / COMMAND with section headers

Action items so far have a single tuple shape `(label, action)`. To support non-selectable section headers and the blank separator, switch to a richer record so the menu loop can distinguish items.

**Files:**
- Modify: `showbible/cli.py:741-808` (`_workflow_tui` draw loop)
- Modify: `showbible/cli.py:906-917` (`_dashboard_actions`)
- Test: `tests/test_showbible.py`

- [ ] **Step 1: Write the failing test for the new menu structure**

Append to `tests/test_showbible.py`:

```python
def test_dashboard_actions_split_into_navigate_and_command() -> None:
    from showbible.cli import _dashboard_actions

    rows = _dashboard_actions("S01E01")
    kinds = [(row["kind"], row.get("label", ""), row.get("action", "")) for row in rows]

    assert kinds == [
        ("header", "NAVIGATE", ""),
        ("nav", "Episodes", "episodes"),
        ("nav", "Cast", "cast"),
        ("nav", "Arc", "arc"),
        ("nav", "Lore", "lore"),
        ("nav", "Outputs", "outputs"),
        ("blank", "", ""),
        ("header", "COMMAND", ""),
        ("cmd", "Run S01E01", "run"),
        ("cmd", "Snapshot", "snapshot"),
        ("cmd", "Doctor", "doctor"),
        ("cmd", "Quit", "quit"),
    ]
```

- [ ] **Step 2: Run it, expect failure (returns the old shape)**

```bash
python -m pytest tests/test_showbible.py::test_dashboard_actions_split_into_navigate_and_command -v
```

- [ ] **Step 3: Replace `_dashboard_actions`**

Replace the current implementation at `showbible/cli.py:906-917` with:

```python
def _dashboard_actions(episode_id: str) -> list[dict[str, str]]:
    return [
        {"kind": "header", "label": "NAVIGATE"},
        {"kind": "nav", "label": "Episodes", "action": "episodes"},
        {"kind": "nav", "label": "Cast", "action": "cast"},
        {"kind": "nav", "label": "Arc", "action": "arc"},
        {"kind": "nav", "label": "Lore", "action": "lore"},
        {"kind": "nav", "label": "Outputs", "action": "outputs"},
        {"kind": "blank"},
        {"kind": "header", "label": "COMMAND"},
        {"kind": "cmd", "label": f"Run {episode_id}", "action": "run"},
        {"kind": "cmd", "label": "Snapshot", "action": "snapshot"},
        {"kind": "cmd", "label": "Doctor", "action": "doctor"},
        {"kind": "cmd", "label": "Quit", "action": "quit"},
    ]
```

Keep `.get("label", "")` and `.get("action", "")` in the test — non-selectable rows omit those keys.

- [ ] **Step 4: Update the `_workflow_tui` draw + key loop**

Modify `_workflow_tui` (around `cli.py:741-808`) so it works with the new records. Replace the inner `draw` function body that iterates `actions` with:

```python
            actions = _dashboard_actions(state["episode_id"])
            selectable_indices = [i for i, row in enumerate(actions) if row["kind"] in {"nav", "cmd"}]
            if not selectable_indices:
                return 0
            if selected not in selectable_indices:
                selected = selectable_indices[0]
            screen.erase()
            height, width = screen.getmaxyx()
            menu_width = max(28, min(42, width // 3))
            screen.addnstr(0, 0, f"ShowBible dashboard - {vault.name}", width - 1, curses.A_BOLD)
            screen.addnstr(1, 0, "enter run  [/] episode  r refresh  q quit", width - 1)
            for index, row in enumerate(actions[: max(0, height - 4)]):
                kind = row["kind"]
                if kind == "header":
                    screen.addnstr(index + 3, 0, row["label"], menu_width - 1, curses.A_BOLD)
                elif kind == "blank":
                    continue
                else:
                    label = "  " + row["label"]
                    attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
                    screen.addnstr(index + 3, 0, label, menu_width - 1, attr)
            panel_x = min(menu_width + 2, width - 1)
            panel_width = max(1, width - panel_x)
            for index, line in enumerate(_dashboard_panel_lines(vault, state["episode_id"], state["message"])):
                if index + 3 >= height:
                    break
                attr = curses.A_BOLD if line.endswith(":") else curses.A_NORMAL
                screen.addnstr(index + 3, panel_x, line, panel_width - 1, attr)
            key = screen.getch()
            if key in (ord("q"), 27):
                return 0
            if key == ord("r"):
                state["message"] = "Refreshed."
                continue
            if key == ord("["):
                state["episode_id"] = _adjacent_episode(vault, state["episode_id"], -1)
                _write_room_state(vault, "planning", episode_id=state["episode_id"])
                state["message"] = f"Selected {state['episode_id']}."
                continue
            if key == ord("]"):
                state["episode_id"] = _adjacent_episode(vault, state["episode_id"], 1)
                _write_room_state(vault, "planning", episode_id=state["episode_id"])
                state["message"] = f"Selected {state['episode_id']}."
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                later = [i for i in selectable_indices if i > selected]
                if later:
                    selected = later[0]
            elif key in (curses.KEY_UP, ord("k")):
                earlier = [i for i in selectable_indices if i < selected]
                if earlier:
                    selected = earlier[-1]
            elif key in (curses.KEY_ENTER, 10, 13):
                action = actions[selected]["action"]
                if action == "quit":
                    return 0
                if action == "run":
                    state["message"] = _run_dashboard_live(screen, vault, state["episode_id"], provider)
                elif action == "outputs":
                    state["message"] = _episode_outputs_tui(screen, vault, state["episode_id"])
                elif action == "cast":
                    state["message"] = _cast_tui(screen, vault, state["episode_id"], provider)
                elif action == "episodes":
                    state["episode_id"], state["message"] = _episodes_tui(screen, vault, state["episode_id"])
                elif action == "arc":
                    state["message"] = _arc_tui(screen, vault, state["episode_id"], provider)
                elif action == "lore":
                    state["message"] = _lore_tui(screen, vault, state["episode_id"], provider)
                else:
                    state["episode_id"], state["message"] = _run_dashboard_action(
                        vault,
                        state["episode_id"],
                        action,
                        provider,
                        prompt=lambda label, default="": _prompt_dashboard_line(screen, label, default),
                    )
```

`_arc_tui` and `_lore_tui` will be added in Tasks 10 and 11; commit anyway with placeholder forward references — Python tolerates this because the calls only fire at runtime when those menu items are selected. Add a guarded stub to keep the module importable:

```python
def _arc_tui(screen: "curses.window", vault: Path, episode_id: str, provider: str) -> str:
    return "Arc sub-screen not implemented yet."


def _lore_tui(screen: "curses.window", vault: Path, episode_id: str, provider: str) -> str:
    return "Lore sub-screen not implemented yet."
```

These stubs are removed/replaced by the real implementations in the next two tasks.

- [ ] **Step 5: Update `_dashboard_actions` consumers**

Search for any other place that destructures the old tuple shape:

```bash
grep -n "_dashboard_actions" showbible/cli.py
```

The only caller is `_workflow_tui`, already rewritten above. Confirm the output of grep shows just the definition + that one call.

- [ ] **Step 6: Run the new test plus the full suite**

```bash
python -m pytest tests/test_showbible.py::test_dashboard_actions_split_into_navigate_and_command -v
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

Expected: both green.

- [ ] **Step 7: Commit**

```bash
git add showbible/cli.py tests/test_showbible.py
git commit -m "feat(tui): split dashboard menu into NAVIGATE and COMMAND"
```

---

## Stage 5 — Sub-screens

### Task 10: `_arc_tui` sub-screen

Mirror `_cast_tui`'s two-pane layout. Beats are listed across all arcs in `vault/arcs/*.md`; the bottom-of-list `+ Add new beat` row prompts arc/episode/status/text. The `s` AI suggest hotkey delegates to a new `_arc_suggest_tui` modelled on the existing `_cast_suggest_tui` ([cli.py:1680-1728](showbible/cli.py)) — background thread + spinner during generation, then `_pick_items_screen` for in-TUI selection of which beats to apply.

**Files:**
- Modify: `showbible/cli.py` (replace the `_arc_tui` stub from Task 9 with the full implementation; place near `_cast_tui` around line 1585)

- [ ] **Step 1: Replace the `_arc_tui` stub**

Locate the `_arc_tui` stub added in Task 9 and replace it with:

```python
def _arc_tui(screen: "curses.window", vault: Path, episode_id: str, provider: str) -> str:
    selected = 0
    message = "Arc manager"
    while True:
        beats = arc_beats(vault)
        items: list[dict[str, object]] = [{"kind": "beat", "beat": b} for b in beats]
        items.append({"kind": "add"})
        selected = max(0, min(selected, len(items) - 1))
        screen.erase()
        height, width = screen.getmaxyx()
        menu_width = max(28, min(48, width // 3))
        screen.addnstr(0, 0, f"Arc - {vault.name}", width - 1, curses.A_BOLD)
        screen.addnstr(1, 0, "j/k move  a add  e edit  d delete  s AI suggest  q return", width - 1)
        max_list = max(0, height - 4)
        for index, item in enumerate(items[:max_list]):
            attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
            if item["kind"] == "add":
                screen.addnstr(index + 3, 0, "+ Add new beat", menu_width - 1, attr)
            else:
                beat = item["beat"]
                line = f"[{beat.arc}] {beat.episode} [{beat.status}] {beat.beat}"
                screen.addnstr(index + 3, 0, line, menu_width - 1, attr)
        panel_x = min(menu_width + 2, width - 1)
        panel_width = max(1, width - panel_x)
        if items[selected]["kind"] == "beat":
            beat = items[selected]["beat"]
            lines = [
                f"arc: {beat.arc}",
                f"episode: {beat.episode}",
                f"status: {beat.status}",
                f"beat: {beat.beat}",
                f"file: arcs/{beat.arc}.md",
            ]
        else:
            lines = ["Add a new beat to any arc."]
        for index, line in enumerate(lines[:max_list]):
            screen.addnstr(index + 3, panel_x, line, panel_width - 1)
        key = screen.getch()
        if key in (ord("q"), 27):
            return message
        if key in (curses.KEY_DOWN, ord("j")):
            selected = min(len(items) - 1, selected + 1)
        elif key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key == ord("a") or (key in (curses.KEY_ENTER, 10, 13) and items[selected]["kind"] == "add"):
            arc_slug = _prompt_dashboard_line(screen, "Arc slug", "season-theme") or "season-theme"
            ep = _prompt_dashboard_line(screen, "Episode id", episode_id) or episode_id
            status = _prompt_dashboard_line(screen, "Status", "planned") or "planned"
            beat_text = _prompt_dashboard_line(screen, "Beat text", "")
            if beat_text:
                add_arc_beat(vault, arc_slug, ep, status, beat_text)
                message = f"Added beat to {arc_slug}: {ep} [{status}] {beat_text}"
            else:
                message = "Cancelled: beat text is required."
        elif key == ord("e") and items[selected]["kind"] == "beat":
            beat = items[selected]["beat"]
            new_ep = _prompt_dashboard_line(screen, "Episode id", beat.episode) or beat.episode
            new_status = _prompt_dashboard_line(screen, "Status", beat.status) or beat.status
            new_text = _prompt_dashboard_line(screen, "Beat text", beat.beat) or beat.beat
            try:
                update_arc_beat(
                    vault,
                    arc_slug=beat.arc,
                    episode_id=beat.episode,
                    original_beat=beat.beat,
                    new_episode_id=new_ep,
                    new_status=new_status,
                    new_beat=new_text,
                )
                message = f"Updated beat in {beat.arc}."
            except VaultError as exc:
                message = f"Edit failed: {exc}"
        elif key == ord("d") and items[selected]["kind"] == "beat":
            beat = items[selected]["beat"]
            confirm = _prompt_dashboard_line(screen, f"Delete beat '{beat.beat[:40]}'? (y/N)", "")
            if (confirm or "").strip().lower() == "y":
                try:
                    remove_arc_beat(vault, beat.arc, beat.episode, beat.beat)
                    message = f"Deleted beat from {beat.arc}."
                    selected = max(0, selected - 1)
                except VaultError as exc:
                    message = f"Delete failed: {exc}"
            else:
                message = "Delete cancelled."
        elif key == ord("s"):
            arc_slug = items[selected]["beat"].arc if items[selected]["kind"] == "beat" else "season-theme"
            message = _arc_suggest_tui(screen, vault, episode_id, provider, arc_slug)
```

Add `VaultError` and `ArcBeat` to the `from showbible.vault import …` block in `cli.py` if not already present.

Then add the helper that gives the user a visible spinner while the model runs and an interactive picker for the result. Place it directly below `_arc_tui`:

```python
def _arc_suggest_tui(
    screen: "curses.window",
    vault: Path,
    episode_id: str,
    provider: str,
    arc_slug: str,
) -> str:
    suggestions: list[dict[str, str]] = []
    error: str | None = None
    lock = threading.Lock()
    done = False

    def worker() -> None:
        nonlocal suggestions, error, done
        try:
            suggestions = _generate_arc_suggestions(vault, episode_id, provider, arc_slug=arc_slug)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        finally:
            with lock:
                done = True

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    spinner = "|/-\\"
    tick = 0
    screen.nodelay(True)
    try:
        while True:
            with lock:
                if done:
                    break
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(0, 0, f"AI Arc Suggestions - {arc_slug}", width - 1, curses.A_BOLD)
            screen.addnstr(2, 0, f"Generating suggestions... {spinner[tick % len(spinner)]}", width - 1)
            tick += 1
            time.sleep(0.15)
    finally:
        screen.nodelay(False)
    if error:
        return f"Suggestion failed: {error}"
    if not suggestions:
        return "No suggestions returned."
    picked = _pick_items_screen(
        screen,
        suggestions,
        f"Select arc beat suggestions to apply to {arc_slug}",
        lambda item: f"{item.get('episode')} [{item.get('status')}] {item.get('beat')}",
    )
    if picked:
        applied = _apply_arc_suggestions(vault, arc_slug, picked)
        return f"Applied {applied} arc beat suggestion(s) to {arc_slug}."
    return "No suggestions applied."
```

- [ ] **Step 2: Manual smoke check that the module still imports**

```bash
python -c "from showbible import cli; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Run the full suite to confirm no regressions**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add showbible/cli.py
git commit -m "feat(tui): add Arc sub-screen with full management"
```

---

### Task 11: `_lore_tui` sub-screen

Same shape as `_arc_tui` but flatter (no arc dimension).

**Files:**
- Modify: `showbible/cli.py` (replace the `_lore_tui` stub from Task 9)

- [ ] **Step 1: Replace the `_lore_tui` stub**

```python
def _lore_tui(screen: "curses.window", vault: Path, episode_id: str, provider: str) -> str:
    selected = 0
    message = "Lore manager"
    while True:
        facts = lore_facts(vault)
        items: list[dict[str, object]] = [{"kind": "fact", "fact": f} for f in facts]
        items.append({"kind": "add"})
        selected = max(0, min(selected, len(items) - 1))
        screen.erase()
        height, width = screen.getmaxyx()
        menu_width = max(28, min(48, width // 3))
        screen.addnstr(0, 0, f"Lore - {vault.name}", width - 1, curses.A_BOLD)
        screen.addnstr(1, 0, "j/k move  a add  e edit  d delete  s AI suggest  q return", width - 1)
        max_list = max(0, height - 4)
        for index, item in enumerate(items[:max_list]):
            attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
            if item["kind"] == "add":
                screen.addnstr(index + 3, 0, "+ Add new fact", menu_width - 1, attr)
            else:
                screen.addnstr(index + 3, 0, item["fact"].text, menu_width - 1, attr)
        panel_x = min(menu_width + 2, width - 1)
        panel_width = max(1, width - panel_x)
        if items[selected]["kind"] == "fact":
            fact = items[selected]["fact"]
            lines = [
                f"fact: {fact.text}",
                f"source: {fact.source}",
                "file: lore-bible/canon.md",
            ]
        else:
            lines = ["Add a new canon fact."]
        for index, line in enumerate(lines[:max_list]):
            screen.addnstr(index + 3, panel_x, line, panel_width - 1)
        key = screen.getch()
        if key in (ord("q"), 27):
            return message
        if key in (curses.KEY_DOWN, ord("j")):
            selected = min(len(items) - 1, selected + 1)
        elif key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key == ord("a") or (key in (curses.KEY_ENTER, 10, 13) and items[selected]["kind"] == "add"):
            text = _prompt_dashboard_line(screen, "Fact", "")
            if not text:
                message = "Cancelled: fact is required."
                continue
            source = _prompt_dashboard_line(screen, "Source", episode_id or "manual") or "manual"
            add_lore_fact(vault, text, source=source)
            message = f"Added fact (source {source})."
        elif key == ord("e") and items[selected]["kind"] == "fact":
            fact = items[selected]["fact"]
            new_text = _prompt_dashboard_line(screen, "Fact", fact.text) or fact.text
            new_source = _prompt_dashboard_line(screen, "Source", fact.source) or fact.source
            try:
                update_lore_fact(
                    vault,
                    original_text=fact.text,
                    new_text=new_text,
                    new_source=new_source,
                )
                message = "Updated fact."
            except VaultError as exc:
                message = f"Edit failed: {exc}"
        elif key == ord("d") and items[selected]["kind"] == "fact":
            fact = items[selected]["fact"]
            confirm = _prompt_dashboard_line(screen, f"Delete '{fact.text[:40]}'? (y/N)", "")
            if (confirm or "").strip().lower() == "y":
                try:
                    remove_lore_fact(vault, fact.text)
                    message = "Deleted fact."
                    selected = max(0, selected - 1)
                except VaultError as exc:
                    message = f"Delete failed: {exc}"
            else:
                message = "Delete cancelled."
        elif key == ord("s"):
            message = _lore_suggest_tui(screen, vault, episode_id, provider)
```

Add `LoreFact` to the `from showbible.vault import …` line in `cli.py` (and confirm `update_lore_fact`, `remove_lore_fact` are already imported from Tasks 5–6).

Then add a sibling helper, modelled on `_arc_suggest_tui` and `_cast_suggest_tui`, that animates while the model runs and uses `_pick_items_screen` for selection. Place it directly below `_lore_tui`:

```python
def _lore_suggest_tui(
    screen: "curses.window",
    vault: Path,
    episode_id: str,
    provider: str,
) -> str:
    suggestions: list[dict[str, str]] = []
    error: str | None = None
    lock = threading.Lock()
    done = False

    def worker() -> None:
        nonlocal suggestions, error, done
        try:
            suggestions = _generate_lore_suggestions(vault, episode_id, provider)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        finally:
            with lock:
                done = True

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    spinner = "|/-\\"
    tick = 0
    screen.nodelay(True)
    try:
        while True:
            with lock:
                if done:
                    break
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(0, 0, "AI Lore Suggestions", width - 1, curses.A_BOLD)
            screen.addnstr(2, 0, f"Generating suggestions... {spinner[tick % len(spinner)]}", width - 1)
            tick += 1
            time.sleep(0.15)
    finally:
        screen.nodelay(False)
    if error:
        return f"Suggestion failed: {error}"
    if not suggestions:
        return "No suggestions returned."
    picked = _pick_items_screen(
        screen,
        suggestions,
        "Select lore fact suggestions to apply",
        lambda item: str(item.get("fact", "")),
    )
    if picked:
        applied = _apply_lore_suggestions(vault, picked, source=episode_id or "manual")
        return f"Applied {applied} lore fact suggestion(s)."
    return "No suggestions applied."
```

- [ ] **Step 2: Smoke import check**

```bash
python -c "from showbible import cli; print('ok')"
```

- [ ] **Step 3: Run the full suite**

```bash
python -m pytest tests/test_showbible.py 2>&1 | tail -10
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add showbible/cli.py
git commit -m "feat(tui): add Lore sub-screen with full management"
```

---

## Stage 6 — Final verification

### Task 12: End-to-end smoke

**Files:**
- Read-only sanity checks; no edits expected unless something is broken.

- [ ] **Step 1: Full test suite**

```bash
python -m pytest -q
```

Expected: all tests green.

- [ ] **Step 2: CLI surface check — no syntax/argparse regressions**

```bash
python -m showbible --help > /dev/null
python -m showbible arcs suggest --help > /dev/null
python -m showbible lore suggest --help > /dev/null
```

Expected: each exits 0 with no traceback.

- [ ] **Step 3: Manual TUI smoke (interactive — only run if a real terminal is available)**

```bash
mkdir -p /tmp/showbible-smoke && rm -rf /tmp/showbible-smoke/demo
python -m showbible init --vault /tmp/showbible-smoke/demo --show "Smoke Show"
python -m showbible tui --vault /tmp/showbible-smoke/demo --episode S01E01 --provider mock
```

Manually verify in the dashboard that:
- The menu shows two labelled sections (NAVIGATE, COMMAND) with a blank between.
- Up/down arrows skip past `NAVIGATE`, the blank row, and `COMMAND` headers.
- `Episodes`, `Cast`, `Arc`, `Lore`, `Outputs` each open their respective sub-screen.
- Inside `Arc`, `a` adds a beat and the new beat appears in the list and in `arcs/season-theme.md`.
- Inside `Lore`, `a` adds a fact and it appears in the list and in `lore-bible/canon.md`.
- `e` edits and `d` deletes work in both sub-screens.
- `s` in either sub-screen produces visible suggestions (with `--provider mock` the fallback seed is what shows up).
- `Snapshot`, `Doctor`, `Run` still work from the COMMAND section.
- `q` from any sub-screen returns to the dashboard; `q` at the dashboard exits.

Press `q` to exit when done.

- [ ] **Step 4: No commit needed if everything passed; otherwise file a follow-up issue.**

---

## Non-goals (explicitly out of scope, do not implement)
- Web UI changes (`showbible/server.py`, `showbible/ui/index.html`).
- Re-styling the right-hand status panel.
- Multi-arc drill-down sub-screen (spec chose flat list).
- Adding `--pick` interactive picker support inside the TUI sub-screens.
- Migrating any on-disk file formats.
