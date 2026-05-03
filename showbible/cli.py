from __future__ import annotations

import argparse
import contextlib
import curses
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .engine import run_episode
from .providers import ProviderError, resolve_provider
from .server import serve, status_payload, transcript_text
from .vault import (
    VaultError,
    CastRole,
    add_cast_role,
    add_episode_cast_role,
    atomic_write_json,
    atomic_write_text,
    cast_roles,
    copy_episode,
    doctor,
    effective_cast_roles,
    ensure_episode,
    episode_cast_roles,
    init_vault,
    infer_episode_id,
    list_episodes,
    people,
    read_json,
    remove_episode_cast_role,
    remove_cast_role,
    resolve_vault,
    slugify,
    write_person,
)

EXIT_GENERIC = 1
EXIT_USAGE = 2
EXIT_VAULT = 3
EXIT_INTEGRITY = 4
EXIT_PROVIDER = 5

CAST_KINDS = {
    "showrunner": "Leads season taste, theme, and final calls.",
    "director": "Breaks scenes, frames conflict, and integrates polish.",
    "writer": "Drafts pitches, beats, dialogue, and alternate scene turns.",
    "actor": "Protects a character voice; use --plays for the character slug.",
    "lore-keeper": "Checks continuity, canon, callbacks, and arc consistency.",
    "producer": "Steers constraints, budget, audience, and franchise fit.",
    "guest-writer": "Episode-specific outside voice or specialist pass.",
}

HELP_TOPICS = {
    "cast": """Cast workflow

Scope follows your current folder:
  show root                  edits pack.yaml roles
  episodes/S01E03            edits that episode's meta.json cast_overrides

Commands:
  showbible cast list
  showbible cast kinds
  showbible cast add "Edie Falco" --kind actor --plays carmela
  showbible cast remove edie-falco
  showbible cast suggest
  showbible cast suggest --pick
  showbible cast suggest --json

Suggestions exclude the current effective cast. In a terminal, suggest opens
a picker; use space to select, enter to apply, q to cancel.
""",
    "episodes": """Episode workflow

Commands:
  showbible episode new S01E01
  showbible episode list
  showbible episode show S01E01
  showbible episode fork S01E01 S01E01-alt
  showbible workflow --episode S01E01
  showbible tui --episode S01E01
  showbible run --episode S01E01
  showbible continue

Episode folders can override show-level cast:
  cd episodes/S01E01
  showbible cast add "Guest Director" --kind director
""",
    "arcs": """Arc workflow

Arcs are markdown files in arcs/*.md. The default vault starts with
arcs/season-theme.md.

Commands:
  showbible arcs
  showbible arcs list
  showbible arcs current --episode S01E01
  showbible arcs show season-theme
  showbible arcs add "Pilot establishes the central argument" --episode S01E01

Scope follows your current folder. From episodes/S01E01, arcs current and arcs
add target S01E01 unless --episode is passed.
""",
    "roles": "Cast role kinds:\n"
    + "\n".join(f"  {kind:<12} {description}" for kind, description in CAST_KINDS.items()),
    "ai": """AI workflow

Default provider:
  LM Studio at http://127.0.0.1:1234
  model google/gemma-4-e4b

Useful commands:
  showbible cast suggest
  showbible run --episode S01E01
  showbible run --provider mock --episode S01E01

Environment overrides:
  LMSTUDIO_BASE_URL
  LMSTUDIO_MODEL
  LMSTUDIO_MAX_TOKENS
""",
    "tui": """Terminal UI

Use the guided workflow TUI as a persistent show dashboard:
  showbible tui
  showbible workflow

It stays open until you press q. The dashboard can create/select episodes,
add show or episode cast, apply AI cast suggestions, add arc beats, add lore
facts, run the selected episode, and run doctor.

Cast suggestions also use a TUI automatically when stdout/stdin are real terminals.
You can force cast picking with:
  showbible cast suggest --pick

Keys:
  up/down or k/j   move
  enter            run command / apply
  [ and ]          switch selected episode
  space            toggle selection in pickers
  a                select all in pickers
  q                cancel
""",
    "lore": """Lore workflow

Lore starts as markdown files in the vault:
  lore-bible/canon.md
  lore-bible/glossary.md
  lore-bible/relationships.md
  arcs/*.md

Episode runs append continuity-check output to canon.md. Manual facts can be
added from the CLI:
  showbible lore
  showbible lore explain
  showbible lore paths
  showbible lore add "Tony owes Junior a debt" --source S01E01

Current v0 behavior is append-only canon. Future review/TUI flows should split
proposed lore from accepted canon before writing.
""",
    "workflow": """Guided workflow

Minimum path for a first episode:
  showbible init Sopranos --from "The Sopranos"
  cd Sopranos
  showbible workflow --episode S01E01

The workflow creates the episode folder if needed, shows current cast, shows
episode-relevant arcs, and offers the next commands. In a real terminal it opens
a persistent dashboard; in noninteractive shells it prints the same minimum
checklist.
""",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="showbible", description="Local-first AI writers room framework.")
    sub = parser.add_subparsers(dest="command")

    help_cmd = sub.add_parser("help", help="show detailed workflow help")
    help_cmd.add_argument("topic", nargs="?", choices=["cast", "episodes", "arcs", "roles", "ai", "tui", "lore", "workflow"])
    help_cmd.set_defaults(func=cmd_help)

    init = sub.add_parser("init", help="scaffold a ShowBible vault")
    init.add_argument("name", help="target directory")
    init.add_argument("--from", dest="from_show", help="seed the pack for a show name")
    init.add_argument("--force", action="store_true", help="allow initialization in a non-empty directory")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="show vault status")
    add_vault_flag(status)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    doctor_cmd = sub.add_parser("doctor", help="diagnose vault integrity")
    add_vault_flag(doctor_cmd)
    doctor_cmd.add_argument("--json", action="store_true")
    doctor_cmd.set_defaults(func=cmd_doctor)

    run = sub.add_parser("run", help="run an episode pipeline")
    add_vault_flag(run)
    run.add_argument("--episode", default="S01E01")
    run.add_argument("--season", action="store_true", help="run all known episodes, or create S01E01 if none exist")
    run.add_argument("--provider", default="lmstudio")
    run.add_argument("--note", action="append", default=[])
    run.add_argument("--speak-as", action="append", default=[])
    run.add_argument("--keep-going", action="store_true", help="accepted for CLI compatibility; v0 runs synchronously")
    run.set_defaults(func=cmd_run)

    attach = sub.add_parser("attach", help="serve the local web UI")
    add_vault_flag(attach)
    attach.add_argument("--host", default="127.0.0.1")
    attach.add_argument("--port", type=int, default=0)
    attach.add_argument("--once", action="store_true", help="print a server smoke payload and exit")
    attach.set_defaults(func=cmd_attach)

    pause = sub.add_parser("pause", help="mark the vault paused")
    add_vault_flag(pause)
    pause.set_defaults(func=cmd_pause)

    resume = sub.add_parser("resume", help="mark the vault running")
    add_vault_flag(resume)
    resume.set_defaults(func=cmd_resume)

    cont = sub.add_parser("continue", help="resume by running the next incomplete episode")
    add_vault_flag(cont)
    cont.add_argument("--episode")
    cont.add_argument("--provider", default="lmstudio")
    cont.set_defaults(func=cmd_continue)

    transcript = sub.add_parser("transcript", help="print episode transcript")
    add_vault_flag(transcript)
    transcript.add_argument("episode", nargs="?")
    transcript.set_defaults(func=cmd_transcript)

    workflow = sub.add_parser("workflow", help="guided episode setup and room workflow")
    add_vault_flag(workflow)
    workflow.add_argument("--episode", default="S01E01")
    workflow.add_argument("--provider", default="lmstudio")
    workflow.add_argument("--no-tui", action="store_true", help="print the workflow instead of opening the terminal UI")
    workflow.set_defaults(func=cmd_workflow)

    tui = sub.add_parser("tui", help="open the guided terminal UI")
    add_vault_flag(tui)
    tui.add_argument("--episode", default="S01E01")
    tui.add_argument("--provider", default="lmstudio")
    tui.add_argument("--no-tui", action="store_true", help="print the workflow instead of opening the terminal UI")
    tui.set_defaults(func=cmd_workflow)

    lore = sub.add_parser("lore", help="inspect and administer lore")
    add_vault_flag(lore)
    lore_sub = lore.add_subparsers(dest="lore_command")
    lore_show = lore_sub.add_parser("show", help="print canon lore")
    add_vault_flag(lore_show)
    lore_show.set_defaults(func=cmd_lore_show)
    lore_explain = lore_sub.add_parser("explain", help="explain how lore is created")
    add_vault_flag(lore_explain)
    lore_explain.set_defaults(func=cmd_lore_explain)
    lore_add = lore_sub.add_parser("add", help="append a canon fact")
    add_vault_flag(lore_add)
    lore_add.add_argument("fact")
    lore_add.add_argument("--source", default="manual")
    lore_add.set_defaults(func=cmd_lore_add)
    lore_paths = lore_sub.add_parser("paths", help="show lore files")
    add_vault_flag(lore_paths)
    lore_paths.set_defaults(func=cmd_lore_paths)
    lore.set_defaults(func=cmd_lore)

    arcs = sub.add_parser("arcs", help="inspect and administer arcs")
    add_vault_flag(arcs)
    arcs.add_argument("--episode", help="episode scope for current arc context")
    arcs_sub = arcs.add_subparsers(dest="arcs_command")
    arcs_list = arcs_sub.add_parser("list", help="list arcs")
    add_vault_flag(arcs_list)
    arcs_list.add_argument("--episode", help="episode scope for current arc context")
    arcs_list.set_defaults(func=cmd_arcs_list)
    arcs_current = arcs_sub.add_parser("current", help="show episode-relevant arcs")
    add_vault_flag(arcs_current)
    arcs_current.add_argument("--episode", help="episode scope; defaults from cwd or room state")
    arcs_current.set_defaults(func=cmd_arcs_current)
    arcs_show = arcs_sub.add_parser("show", help="print an arc file")
    add_vault_flag(arcs_show)
    arcs_show.add_argument("arc", nargs="?", default="season-theme")
    arcs_show.set_defaults(func=cmd_arcs_show)
    arcs_add = arcs_sub.add_parser("add", help="add an episode beat to an arc")
    add_vault_flag(arcs_add)
    arcs_add.add_argument("beat")
    arcs_add.add_argument("--arc", default="season-theme")
    arcs_add.add_argument("--episode", help="episode target; defaults from cwd or S01E01")
    arcs_add.add_argument("--status", default="planned")
    arcs_add.set_defaults(func=cmd_arcs_add)
    arcs.set_defaults(func=cmd_arcs)

    cost = sub.add_parser("cost", help="print cost ledger")
    add_vault_flag(cost)
    cost.add_argument("--json", action="store_true")
    cost.set_defaults(func=cmd_cost)

    pack = sub.add_parser("pack", help="show pack management")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    pack_list = pack_sub.add_parser("list")
    add_vault_flag(pack_list)
    pack_list.set_defaults(func=cmd_pack_list)
    pack_add = pack_sub.add_parser("add")
    add_vault_flag(pack_add)
    pack_add.add_argument("show")
    pack_add.add_argument("--from", dest="from_url")
    pack_add.set_defaults(func=cmd_pack_add)
    pack_edit = pack_sub.add_parser("edit")
    add_vault_flag(pack_edit)
    pack_edit.add_argument("person_slug")
    pack_edit.set_defaults(func=cmd_pack_edit)
    pack_export = pack_sub.add_parser("export")
    add_vault_flag(pack_export)
    pack_export.set_defaults(func=cmd_pack_export)

    cast = sub.add_parser("cast", help="inspect, set, or AI-suggest cast")
    add_vault_flag(cast)
    cast.add_argument("--auto", action="store_true", help="show the current auto-selected cast")
    cast_sub = cast.add_subparsers(dest="cast_command")
    cast_list = cast_sub.add_parser("list")
    add_vault_flag(cast_list)
    add_cast_scope_flags(cast_list)
    cast_list.set_defaults(func=cmd_cast_list)
    cast_kinds = cast_sub.add_parser("kinds", help="list supported cast role kinds")
    cast_kinds.set_defaults(func=cmd_cast_kinds)
    cast_add = cast_sub.add_parser("add")
    add_vault_flag(cast_add)
    add_cast_scope_flags(cast_add)
    cast_add.add_argument("display_name")
    cast_add.add_argument("--person", help="person slug; defaults from display name")
    cast_add.add_argument("--kind", default="actor", help="showrunner, director, writer, actor, lore-keeper")
    cast_add.add_argument("--plays", help="character slug for actor roles")
    cast_add.set_defaults(func=cmd_cast_add)
    cast_remove = cast_sub.add_parser("remove")
    add_vault_flag(cast_remove)
    add_cast_scope_flags(cast_remove)
    cast_remove.add_argument("person_slug")
    cast_remove.set_defaults(func=cmd_cast_remove)
    cast_suggest = cast_sub.add_parser("suggest")
    add_vault_flag(cast_suggest)
    add_cast_scope_flags(cast_suggest)
    cast_suggest.add_argument("show", nargs="?")
    cast_suggest.add_argument("--provider", default="lmstudio")
    cast_suggest.add_argument("--limit", type=int, default=6)
    cast_suggest.add_argument("--apply", action="store_true", help="write suggested people and roles into the vault")
    cast_suggest.add_argument("--pick", action="store_true", help="open a terminal picker for returned suggestions")
    cast_suggest.add_argument("--json", action="store_true", help="print parsed suggestions as JSON")
    cast_suggest.set_defaults(func=cmd_cast_suggest)
    cast.set_defaults(func=cmd_cast)

    episode = sub.add_parser("episode", help="episode lifecycle")
    ep_sub = episode.add_subparsers(dest="episode_command", required=True)
    ep_new = ep_sub.add_parser("new")
    add_vault_flag(ep_new)
    ep_new.add_argument("episode_id", nargs="?", default="S01E01")
    ep_new.set_defaults(func=cmd_episode_new)
    ep_list = ep_sub.add_parser("list")
    add_vault_flag(ep_list)
    ep_list.set_defaults(func=cmd_episode_list)
    ep_show = ep_sub.add_parser("show")
    add_vault_flag(ep_show)
    ep_show.add_argument("episode_id")
    ep_show.add_argument("--json", action="store_true")
    ep_show.set_defaults(func=cmd_episode_show)
    ep_fork = ep_sub.add_parser("fork")
    add_vault_flag(ep_fork)
    ep_fork.add_argument("episode_id")
    ep_fork.add_argument("target_id", nargs="?")
    ep_fork.set_defaults(func=cmd_episode_fork)

    return parser


def add_vault_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault", help="path to a ShowBible vault")


def add_cast_scope_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--episode", help="write/read episode-specific cast overrides")
    parser.add_argument("--show", action="store_true", help="force show-level cast even when cwd is inside an episode")


def cmd_init(args: argparse.Namespace) -> int:
    vault = init_vault(Path(args.name), show_name=args.from_show, force=args.force)
    print(f"Initialized ShowBible vault: {vault}")
    return 0


def cmd_help(args: argparse.Namespace) -> int:
    topic = args.topic
    if not topic:
        print("ShowBible help topics: cast, episodes, arcs, roles, ai, tui, lore, workflow")
        print("Try: showbible help workflow")
        return 0
    print(HELP_TOPICS[topic].strip())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    payload = status_payload(vault)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Vault: {vault}")
        print(f"Cast: {len(payload['cast'])}")
        print(f"Episodes: {len(payload['episodes'])}")
        findings = payload["findings"]
        print(f"Doctor: {'clean' if not findings else str(len(findings)) + ' finding(s)'}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    findings = doctor(vault)
    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2, sort_keys=True))
    elif not findings:
        print("Doctor clean.")
    else:
        for finding in findings:
            print(f"{finding.level}: {finding.path}: {finding.message}")
    return EXIT_INTEGRITY if any(finding.level == "error" for finding in findings) else 0


def cmd_run(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episodes = list_episodes(vault) if args.season else [args.episode]
    if args.season and not episodes:
        episodes = ["S01E01"]
    for episode_id in episodes:
        result = run_episode(vault, episode_id, args.provider, args.note, args.speak_as)
        print(
            f"Ran {result.episode_id}: {len(result.completed_phases)} phase(s), "
            f"{len(result.skipped_phases)} skipped, {result.tokens} token(s)."
        )
    return 0


def cmd_attach(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    result = serve(vault, host=args.host, port=args.port, once=args.once)
    if args.once:
        print(result)
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    _write_room_state(vault, "paused")
    print("Room paused.")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    _write_room_state(vault, "running")
    print("Room resumed.")
    return 0


def cmd_continue(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    room_state = read_json(vault / ".room" / "state.json", {})
    episode = args.episode or room_state.get("current_episode") or (list_episodes(vault) or ["S01E01"])[0]
    result = run_episode(vault, episode, args.provider)
    print(f"Continued {result.episode_id}: {len(result.skipped_phases)} phase(s) already complete.")
    return 0


def cmd_transcript(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    print(transcript_text(vault, args.episode).rstrip())
    return 0


def cmd_workflow(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = args.episode or _current_episode(vault) or "S01E01"
    ensure_episode(vault, episode_id)
    _write_room_state(vault, "planning", episode_id=episode_id)
    if not args.no_tui and sys.stdin.isatty() and sys.stdout.isatty():
        return _workflow_tui(vault, episode_id, args.provider)
    _print_workflow_snapshot(vault, episode_id, args.provider)
    return 0


def cmd_lore(args: argparse.Namespace) -> int:
    if getattr(args, "lore_command", None):
        return int(args.func(args) or 0)
    return cmd_lore_show(args)


def cmd_lore_show(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    print((vault / "lore-bible" / "canon.md").read_text(encoding="utf-8").rstrip())
    return 0


def cmd_lore_explain(args: argparse.Namespace) -> int:
    print(HELP_TOPICS["lore"].strip())
    return 0


def cmd_lore_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    canon = vault / "lore-bible" / "canon.md"
    existing = canon.read_text(encoding="utf-8") if canon.exists() else "# Canon\n\n## Facts\n\n"
    entry = f"\n- **Manual fact** - {args.fact.strip()} *Source: {args.source}*\n"
    atomic_write_text(canon, existing.rstrip() + entry)
    print(f"Added lore fact to {canon}")
    return 0


def cmd_lore_paths(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    paths = [
        vault / "lore-bible" / "canon.md",
        vault / "lore-bible" / "glossary.md",
        vault / "lore-bible" / "relationships.md",
        vault / "arcs",
    ]
    for path in paths:
        print(path)
    return 0


def cmd_arcs(args: argparse.Namespace) -> int:
    if getattr(args, "arcs_command", None):
        return int(args.func(args) or 0)
    return cmd_arcs_list(args)


def cmd_arcs_list(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _arc_episode_scope(vault, args)
    arcs = _arc_summaries(vault)
    if episode_id:
        print(f"Arc context for {episode_id}:")
    if not arcs:
        print("No arcs set.")
        return 0
    for arc in arcs:
        target_count = len(_beats_for_episode(arc["beats"], episode_id)) if episode_id else len(arc["beats"])
        suffix = f" - {target_count} relevant beat(s)" if episode_id else f" - {len(arc['beats'])} beat(s)"
        print(f"{arc['slug']}: {arc['title']}{suffix}")
    return 0


def cmd_arcs_current(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _arc_episode_scope(vault, args) or _current_episode(vault) or "S01E01"
    print(_format_current_arcs(vault, episode_id).rstrip())
    return 0


def cmd_arcs_show(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    path = _arc_path(vault, args.arc)
    if not path.exists():
        raise VaultError(f"Arc not found: {args.arc}")
    print(path.read_text(encoding="utf-8").rstrip())
    return 0


def cmd_arcs_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _arc_episode_scope(vault, args) or "S01E01"
    path = _arc_path(vault, args.arc)
    if not path.exists():
        title = args.arc.replace("-", " ").title()
        atomic_write_text(path, f"# {title}\n\n")
    existing = path.read_text(encoding="utf-8").rstrip()
    if "## Episode Beats" not in existing:
        existing += "\n\n## Episode Beats\n"
    entry = f"\n- {episode_id} [{args.status}] {args.beat.strip()}"
    atomic_write_text(path, existing.rstrip() + entry + "\n")
    print(f"Added arc beat to {path.name}: {episode_id} [{args.status}] {args.beat.strip()}")
    return 0


def _arc_episode_scope(vault: Path, args: argparse.Namespace) -> str | None:
    if getattr(args, "episode", None):
        return args.episode
    return infer_episode_id(vault)


def _current_episode(vault: Path) -> str | None:
    inferred = infer_episode_id(vault)
    if inferred:
        return inferred
    room_state = read_json(vault / ".room" / "state.json", {})
    if room_state.get("current_episode"):
        return str(room_state["current_episode"])
    episodes = list_episodes(vault)
    return episodes[0] if episodes else None


def _arc_path(vault: Path, arc: str) -> Path:
    slug = slugify(arc.removesuffix(".md"))
    return vault / "arcs" / f"{slug}.md"


def _arc_summaries(vault: Path) -> list[dict[str, object]]:
    summaries = []
    for path in sorted((vault / "arcs").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = _markdown_title(text) or path.stem.replace("-", " ").title()
        summaries.append({"slug": path.stem, "title": title, "path": path, "beats": _arc_beats(text)})
    return summaries


def _markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _arc_beats(text: str) -> list[dict[str, str]]:
    beats = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        target = re.match(r"-?\s*episode_target:\s*(.+)$", line)
        if target:
            if current and current.get("beat"):
                beats.append(current)
            current = {"episode": _episode_target_to_id(target.group(1))}
            continue
        if current is not None and line.startswith("beat:"):
            current["beat"] = line.split(":", 1)[1].strip().strip("\"'")
            continue
        if current is not None and line.startswith("status:"):
            current["status"] = line.split(":", 1)[1].strip().strip("\"'")
            continue
        item = re.match(r"-\s*(S\d+E\d+)\s+\[([^\]]+)\]\s+(.+)$", line, flags=re.IGNORECASE)
        if item:
            beats.append({"episode": item.group(1).upper(), "status": item.group(2), "beat": item.group(3)})
    if current and current.get("beat"):
        beats.append(current)
    return beats


def _episode_target_to_id(value: str) -> str:
    cleaned = value.strip().strip("\"'")
    if re.match(r"^S\d+E\d+$", cleaned, flags=re.IGNORECASE):
        return cleaned.upper()
    if cleaned.isdigit():
        return f"S01E{int(cleaned):02d}"
    return cleaned


def _beats_for_episode(beats: object, episode_id: str | None) -> list[dict[str, str]]:
    if not episode_id:
        return list(beats) if isinstance(beats, list) else []
    return [beat for beat in beats if isinstance(beat, dict) and beat.get("episode", "").upper() == episode_id.upper()]


def _format_current_arcs(vault: Path, episode_id: str) -> str:
    lines = [f"Current arcs for {episode_id}:"]
    found = False
    for arc in _arc_summaries(vault):
        relevant = _beats_for_episode(arc["beats"], episode_id)
        if not relevant:
            continue
        found = True
        lines.append(f"{arc['slug']}: {arc['title']}")
        for beat in relevant:
            status = beat.get("status", "planned")
            lines.append(f"  - [{status}] {beat.get('beat', '')}")
    if not found:
        lines.append("No episode-specific arc beats yet.")
        lines.append(f"Add one: showbible arcs add \"Pilot tests the season theme\" --episode {episode_id}")
    return "\n".join(lines) + "\n"


def _format_current_cast(vault: Path, episode_id: str | None = None) -> str:
    people_by_slug = {person["slug"]: person for person in people(vault)}
    roles = effective_cast_roles(vault, episode_id)
    scope = f"episode {episode_id}" if episode_id else "show"
    lines = [f"Current cast ({scope}):"]
    if not roles:
        lines.append("No cast roles set.")
        return "\n".join(lines) + "\n"
    for role in roles:
        display = people_by_slug.get(role.person, {}).get("display_name", role.person)
        plays = f" as {role.plays}" if role.plays else ""
        lines.append(f"  - {role.kind}: {role.person} ({display}){plays}")
    return "\n".join(lines) + "\n"


def _print_workflow_snapshot(vault: Path, episode_id: str, provider: str) -> None:
    print(_workflow_snapshot_text(vault, episode_id, provider).rstrip())


def _workflow_snapshot_text(vault: Path, episode_id: str, provider: str) -> str:
    return "\n".join(
        [
            f"ShowBible workflow for {episode_id}",
            "",
            "Minimum needed:",
            f"  [x] Vault: {vault}",
            f"  [x] Episode folder: {ensure_episode(vault, episode_id)}",
            f"  [x] Current cast visible: showbible cast list --episode {episode_id}",
            f"  [x] Current arcs visible: showbible arcs current --episode {episode_id}",
            "",
            _format_current_cast(vault, episode_id).rstrip(),
            "",
            _format_current_arcs(vault, episode_id).rstrip(),
            "",
            "Next commands:",
            "  showbible tui",
            "  showbible cast suggest --pick",
            f"  showbible cast suggest --episode {episode_id} --pick",
            f"  showbible arcs add \"Pilot tests the season theme\" --episode {episode_id}",
            f"  showbible run --episode {episode_id} --provider {provider}",
            "",
        ]
    )


def _workflow_tui(vault: Path, episode_id: str, provider: str) -> int:
    state = {"episode_id": episode_id, "message": "Dashboard ready. Press q when you are done."}

    def draw(screen: "curses.window") -> int:
        selected = 0
        curses.curs_set(0)
        screen.keypad(True)
        while True:
            actions = _dashboard_actions(state["episode_id"])
            selected = min(selected, len(actions) - 1)
            screen.erase()
            height, width = screen.getmaxyx()
            menu_width = max(28, min(42, width // 3))
            screen.addnstr(0, 0, f"ShowBible dashboard - {vault.name}", width - 1, curses.A_BOLD)
            screen.addnstr(1, 0, "enter run  [/] episode  r refresh  q quit", width - 1)
            for index, (label, _action) in enumerate(actions[: max(0, height - 4)]):
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
                selected = min(len(actions) - 1, selected + 1)
            elif key in (curses.KEY_UP, ord("k")):
                selected = max(0, selected - 1)
            elif key in (curses.KEY_ENTER, 10, 13):
                action = actions[selected][1]
                if action == "quit":
                    return 0
                state["episode_id"], state["message"] = _run_dashboard_action(
                    vault,
                    state["episode_id"],
                    action,
                    provider,
                    prompt=lambda label, default="": _prompt_dashboard_line(screen, label, default),
                )
        return 0

    return curses.wrapper(draw)


def _dashboard_actions(episode_id: str) -> list[tuple[str, str]]:
    return [
        ("Show snapshot", "snapshot"),
        ("Create/select episode", "episode-select"),
        ("Create next episode", "episode-next-new"),
        ("Add show cast", "cast-show-add"),
        (f"Add {episode_id} cast override", "cast-episode-add"),
        ("AI suggest show cast (apply)", "suggest-show-apply"),
        (f"AI suggest {episode_id} cast (apply)", "suggest-episode-apply"),
        (f"Add {episode_id} arc beat", "arc-add"),
        (f"Add {episode_id} lore fact", "lore-add"),
        (f"Run {episode_id}", "run"),
        ("Doctor", "doctor"),
        ("Quit", "quit"),
    ]


def _run_dashboard_action(
    vault: Path,
    episode_id: str,
    action: str,
    provider: str,
    prompt: object | None = None,
) -> tuple[str, str]:
    if action == "snapshot":
        return episode_id, _workflow_snapshot_text(vault, episode_id, provider)
    if action == "episode-select":
        selected = _dashboard_prompt(prompt, "Episode id", episode_id) or episode_id
        ensure_episode(vault, selected)
        _write_room_state(vault, "planning", episode_id=selected)
        return selected, f"Selected episode {selected}."
    if action == "episode-next-new":
        selected = _next_episode_id(list_episodes(vault))
        ensure_episode(vault, selected)
        _write_room_state(vault, "planning", episode_id=selected)
        return selected, f"Created and selected {selected}."
    if action in {"cast-show-add", "cast-episode-add"}:
        display = _dashboard_prompt(prompt, "Display name", "")
        if not display:
            return episode_id, "Cancelled: display name is required."
        kind = _dashboard_prompt(prompt, "Kind", "actor") or "actor"
        plays = _dashboard_prompt(prompt, "Plays/character slug", "") or None
        slug = slugify(display)
        write_person(vault, slug, display, kind, plays)
        role = CastRole(kind=kind, person=slug, plays=plays)
        if action == "cast-episode-add":
            add_episode_cast_role(vault, episode_id, role)
            return episode_id, f"Added {kind} {display} to episode {episode_id}."
        add_cast_role(vault, role)
        return episode_id, f"Added show {kind} {display}."
    if action == "suggest-show-apply":
        output = _capture_cli_output(
            cmd_cast_suggest,
            argparse.Namespace(
                vault=str(vault),
                episode=None,
                show=None,
                provider=provider,
                limit=6,
                apply=True,
                pick=False,
                json=False,
            ),
        )
        return episode_id, output or "Applied show cast suggestions."
    if action == "suggest-episode-apply":
        output = _capture_cli_output(
            cmd_cast_suggest,
            argparse.Namespace(
                vault=str(vault),
                episode=episode_id,
                show=False,
                provider=provider,
                limit=6,
                apply=True,
                pick=False,
                json=False,
            ),
        )
        return episode_id, output or f"Applied {episode_id} cast suggestions."
    if action == "arc-add":
        beat = _dashboard_prompt(prompt, "Arc beat", "Pilot tests the season theme.")
        if not beat:
            return episode_id, "Cancelled: arc beat is required."
        output = _capture_cli_output(
            cmd_arcs_add,
            argparse.Namespace(vault=str(vault), episode=episode_id, arc="season-theme", status="planned", beat=beat),
        )
        return episode_id, output
    if action == "lore-add":
        fact = _dashboard_prompt(prompt, "Lore fact", "")
        if not fact:
            return episode_id, "Cancelled: lore fact is required."
        output = _capture_cli_output(
            cmd_lore_add,
            argparse.Namespace(vault=str(vault), fact=fact, source=episode_id),
        )
        return episode_id, output
    if action == "run":
        output = _capture_cli_output(
            cmd_run,
            argparse.Namespace(
                vault=str(vault),
                episode=episode_id,
                season=False,
                provider=provider,
                note=[],
                speak_as=[],
                keep_going=False,
            ),
        )
        return episode_id, output
    if action == "doctor":
        findings = doctor(vault)
        if not findings:
            return episode_id, "Doctor clean."
        return episode_id, "\n".join(f"{item.level}: {item.path}: {item.message}" for item in findings)
    return episode_id, "No action."


def _dashboard_prompt(prompt: object | None, label: str, default: str = "") -> str | None:
    if prompt is None:
        return default
    value = prompt(label, default)  # type: ignore[operator]
    if value is None:
        return None
    return str(value).strip() or default


def _capture_cli_output(func: object, args: argparse.Namespace) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        func(args)  # type: ignore[operator]
    return buffer.getvalue().strip()


def _prompt_dashboard_line(screen: "curses.window", label: str, default: str = "") -> str | None:
    height, width = screen.getmaxyx()
    prompt = f"{label}"
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    screen.move(max(0, height - 2), 0)
    screen.clrtoeol()
    screen.addnstr(max(0, height - 2), 0, prompt, width - 1, curses.A_BOLD)
    screen.move(max(0, height - 1), 0)
    screen.clrtoeol()
    curses.echo()
    try:
        raw = screen.getstr(max(0, height - 1), 0, max(1, width - 1))
    finally:
        curses.noecho()
    value = raw.decode("utf-8", errors="ignore").strip()
    return value or default


def _dashboard_panel_lines(vault: Path, episode_id: str, message: str) -> list[str]:
    ensure_episode(vault, episode_id)
    meta = read_json(vault / "episodes" / episode_id / "meta.json", {})
    episodes = list_episodes(vault)
    costs = read_json(vault / ".room" / "costs.json", {})
    findings = doctor(vault)
    lines = [
        "Show:",
        f"Vault: {vault}",
        f"Episodes: {', '.join(episodes) or 'none'}",
        f"Selected: {episode_id} ({meta.get('status', 'created')})",
        f"Completed phases: {len(meta.get('completed_phases', []))}",
        f"Cost: {costs.get('total_tokens', 0)} token(s), ${costs.get('total_dollars', 0.0):.4f}",
        f"Doctor: {'clean' if not findings else str(len(findings)) + ' finding(s)'}",
        "",
        "Current Cast:",
    ]
    roles = effective_cast_roles(vault, episode_id)
    people_by_slug = {person["slug"]: person for person in people(vault)}
    if roles:
        for role in roles[:8]:
            display = people_by_slug.get(role.person, {}).get("display_name", role.person)
            plays = f" as {role.plays}" if role.plays else ""
            lines.append(f"- {role.kind}: {display}{plays}")
        if len(roles) > 8:
            lines.append(f"- ... {len(roles) - 8} more")
    else:
        lines.append("- no cast roles set")
    lines.extend(["", "Current Arcs:"])
    lines.extend(_format_current_arcs(vault, episode_id).strip().splitlines()[1:8])
    lines.extend(["", "Last Action:"])
    lines.extend((message or "No action yet.").splitlines()[:10])
    return lines


def _next_episode_id(episodes: list[str]) -> str:
    numbers = []
    for episode in episodes:
        match = re.match(r"^S01E(\d+)$", episode)
        if match:
            numbers.append(int(match.group(1)))
    return f"S01E{(max(numbers) + 1 if numbers else 1):02d}"


def _adjacent_episode(vault: Path, episode_id: str, direction: int) -> str:
    episodes = list_episodes(vault)
    if not episodes:
        ensure_episode(vault, episode_id)
        return episode_id
    if episode_id not in episodes:
        return episodes[0]
    index = episodes.index(episode_id)
    return episodes[(index + direction) % len(episodes)]


def cmd_cost(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    payload = read_json(vault / ".room" / "costs.json", {})
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Total tokens: {payload.get('total_tokens', 0)}")
        print(f"Total dollars: {payload.get('total_dollars', 0.0):.4f}")
    return 0


def cmd_pack_list(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    print(vault.name)
    return 0


def cmd_pack_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    show = args.show
    atomic_write_text(vault / "research" / f"{slugify(show)}.md", f"# {show}\n\nSeeded pack note.\n")
    if args.from_url:
        print(f"Recorded community pack source for {show}: {args.from_url}")
    else:
        print(f"Added starter research note for {show}.")
    return 0


def cmd_pack_edit(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    path = vault / "people" / f"{args.person_slug}.md"
    if not path.exists():
        raise VaultError(f"Person not found: {args.person_slug}")
    editor = os.environ.get("EDITOR")
    if editor:
        return subprocess.call([editor, str(path)])
    print(path)
    return 0


def cmd_pack_export(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    print(f"Pack is filesystem-native and ready to share from: {vault}")
    return 0


def cmd_cast(args: argparse.Namespace) -> int:
    if getattr(args, "cast_command", None):
        return int(args.func(args) or 0)
    return cmd_cast_list(args)


def cmd_cast_list(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _cast_episode_scope(vault, args)
    people_by_slug = {person["slug"]: person for person in people(vault)}
    roles = effective_cast_roles(vault, episode_id)
    if getattr(args, "auto", False):
        print("Auto/current cast:")
    print(f"Scope: {'episode ' + episode_id if episode_id else 'show'}")
    if not roles:
        print("No cast roles set.")
        return 0
    for role in roles:
        display = people_by_slug.get(role.person, {}).get("display_name", role.person)
        plays = f" as {role.plays}" if role.plays else ""
        print(f"{role.kind}: {role.person} ({display}){plays}")
    return 0


def cmd_cast_kinds(args: argparse.Namespace) -> int:
    for kind, description in CAST_KINDS.items():
        print(f"{kind:<12} {description}")
    return 0


def cmd_cast_add(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _cast_episode_scope(vault, args)
    slug = args.person or slugify(args.display_name)
    write_person(vault, slug, args.display_name, args.kind, args.plays)
    role = CastRole(kind=args.kind, person=slug, plays=args.plays)
    if episode_id:
        add_episode_cast_role(vault, episode_id, role)
    else:
        add_cast_role(vault, role)
    print(f"Added {args.kind}: {slug} ({args.display_name}) to {'episode ' + episode_id if episode_id else 'show'}")
    return 0


def cmd_cast_remove(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _cast_episode_scope(vault, args)
    if episode_id:
        remove_episode_cast_role(vault, episode_id, args.person_slug)
    else:
        remove_cast_role(vault, args.person_slug)
    print(f"Removed cast role from {'episode ' + episode_id if episode_id else 'show'}: {args.person_slug}")
    return 0


def cmd_cast_suggest(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode_id = _cast_episode_scope(vault, args)
    pack = (vault / "pack.yaml").read_text(encoding="utf-8")
    show_name = args.show or _show_name_from_pack(pack) or vault.name
    existing_roles = effective_cast_roles(vault, episode_id)
    existing_people = {role.person for role in existing_roles}
    existing_line = ", ".join(sorted(existing_people)) or "none"
    episode_context = ""
    if episode_id:
        episode = ensure_episode(vault, episode_id)
        episode_context = f"\nEpisode scope: {episode_id}\nEpisode meta:\n{json.dumps(read_json(episode / 'meta.json', {}), indent=2)}\n"
    prompt = (
        f"Suggest a compact writers-room cast for {show_name}. Use real public people associated with the show "
        "when you know them: creators, showrunners, directors, writers, and actors. "
        "Do not invent generic labels like Cast Member, TV Writer, or Director. "
        f"Return JSON only: an array of up to {args.limit} objects with keys "
        "kind, person, display_name, and optional plays. Include showrunner, director, writer, and actor roles. "
        "Use lowercase kebab-case for person and plays. The plays value must be one string, never an array. "
        "Return compact complete JSON and do not include prose. "
        f"Exclude these already-cast people: {existing_line}. "
        f"If episode scope is present, suggest additions or overrides for that episode only.\n\n"
        f"Current pack:\n{pack}{episode_context}"
    )
    suggestion_dir = (vault / "episodes" / episode_id) if episode_id else (vault / "research")
    suggestion_path = suggestion_dir / "cast-suggestions.md"
    raw_path = suggestion_dir / "cast-suggestions-raw.md"
    provider = resolve_provider(args.provider)
    try:
        generation = provider.generate("cast-suggest", "cast", prompt)
        try:
            suggestions = _extract_json_array(generation.text)
        except ValueError:
            repair_prompt = (
                prompt
                + "\n\nYour previous output was not valid JSON. Previous output:\n"
                + generation.text
                + "\n\nReturn only one valid JSON array now."
            )
            generation = provider.generate("cast-suggest", "cast", repair_prompt)
            try:
                suggestions = _extract_json_array(generation.text)
            except ValueError as exc:
                atomic_write_text(raw_path, generation.text + "\n")
                raise ValueError(f"AI cast suggestion did not return valid JSON. Raw output saved: {raw_path}") from exc
    except ProviderError as exc:
        suggestions = _fallback_cast_suggestions(show_name, args.limit, existing_people)
        atomic_write_text(raw_path, f"Provider failed: {exc}\n")
    suggestions = _filter_existing_suggestions(suggestions, existing_people)
    if not suggestions:
        refill_prompt = (
            prompt
            + "\n\nAll previous suggestions were already in the cast. Return different people only. "
            + f"Do not include any of: {existing_line}."
        )
        try:
            generation = provider.generate("cast-suggest", "cast", refill_prompt)
            suggestions = _filter_existing_suggestions(_extract_json_array(generation.text), existing_people)
        except (ProviderError, ValueError):
            suggestions = _fallback_cast_suggestions(show_name, args.limit, existing_people)
    atomic_write_text(suggestion_path, f"# Cast Suggestions for {show_name}\n\n```json\n{json.dumps(suggestions, indent=2)}\n```\n")
    if args.apply:
        _apply_cast_suggestions(vault, episode_id, suggestions)
        print(f"Applied {len(suggestions)} cast suggestion(s) to {'episode ' + episode_id if episode_id else 'show'}.")
    elif args.pick or _should_pick(args):
        picked = _pick_cast_suggestions(suggestions, f"{show_name} cast suggestions")
        if picked:
            _apply_cast_suggestions(vault, episode_id, picked)
            print(f"Applied {len(picked)} selected cast suggestion(s) to {'episode ' + episode_id if episode_id else 'show'}.")
        else:
            print("No cast suggestions applied.")
    elif args.json:
        print(json.dumps(suggestions, indent=2, sort_keys=True))
    else:
        print(json.dumps(suggestions, indent=2))
        print(f"Saved suggestions: {suggestion_path}")
        print("Run from a terminal for the picker, or use --pick / --apply / --json.")
    return 0


def _cast_episode_scope(vault: Path, args: argparse.Namespace) -> str | None:
    if getattr(args, "show", False):
        return None
    if getattr(args, "episode", None):
        return args.episode
    return infer_episode_id(vault)


def _show_name_from_pack(pack: str) -> str | None:
    match = re.search(r"^\s*name:\s*(.+)$", pack, flags=re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else None


def _filter_existing_suggestions(
    suggestions: list[dict[str, object]],
    existing_people: set[str],
) -> list[dict[str, object]]:
    filtered = []
    seen = set()
    for item in suggestions:
        slug = str(item.get("person") or slugify(str(item.get("display_name") or "")))
        if not slug or slug in existing_people or slug in seen:
            continue
        item["person"] = slug
        filtered.append(item)
        seen.add(slug)
    return filtered


def _fallback_cast_suggestions(show_name: str, limit: int, existing_people: set[str]) -> list[dict[str, object]]:
    normalized = show_name.lower()
    if "sopranos" in normalized:
        candidates = [
            {"kind": "writer", "person": "terence-winter", "display_name": "Terence Winter"},
            {"kind": "writer", "person": "matthew-weiner", "display_name": "Matthew Weiner"},
            {"kind": "director", "person": "tim-van-patten", "display_name": "Tim Van Patten"},
            {"kind": "director", "person": "allen-coulter", "display_name": "Allen Coulter"},
            {"kind": "actor", "person": "edie-falco", "display_name": "Edie Falco", "plays": "carmela-soprano"},
            {"kind": "actor", "person": "lorraine-bracco", "display_name": "Lorraine Bracco", "plays": "jennifer-melfi"},
            {"kind": "actor", "person": "michael-imperioli", "display_name": "Michael Imperioli", "plays": "christopher-moltisanti"},
        ]
    elif "next generation" in normalized or "star trek" in normalized:
        candidates = [
            {"kind": "showrunner", "person": "michael-piller", "display_name": "Michael Piller"},
            {"kind": "writer", "person": "ronald-d-moore", "display_name": "Ronald D. Moore"},
            {"kind": "director", "person": "jonathan-frakes", "display_name": "Jonathan Frakes"},
            {"kind": "actor", "person": "patrick-stewart", "display_name": "Patrick Stewart", "plays": "picard"},
            {"kind": "actor", "person": "brent-spiner", "display_name": "Brent Spiner", "plays": "data"},
            {"kind": "actor", "person": "levar-burton", "display_name": "LeVar Burton", "plays": "geordi"},
        ]
    else:
        candidates = [
            {"kind": "writer", "person": "research-writer", "display_name": "Research Writer"},
            {"kind": "director", "person": "scene-director", "display_name": "Scene Director"},
            {"kind": "lore-keeper", "person": "lore-keeper", "display_name": "Lore Keeper"},
        ]
    return _filter_existing_suggestions(candidates, existing_people)[:limit]


def _apply_cast_suggestions(vault: Path, episode_id: str | None, suggestions: list[dict[str, object]]) -> None:
    for item in suggestions:
        slug = str(item.get("person") or slugify(str(item.get("display_name") or "person")))
        display = str(item.get("display_name") or slug.replace("-", " ").title())
        kind = str(item.get("kind") or "actor")
        plays_text = _normalize_plays(item.get("plays"))
        write_person(vault, slug, display, kind, plays_text)
        role = CastRole(kind=kind, person=slug, plays=plays_text)
        if episode_id:
            add_episode_cast_role(vault, episode_id, role)
        else:
            add_cast_role(vault, role)


def _should_pick(args: argparse.Namespace) -> bool:
    return not args.json and not args.apply and sys.stdin.isatty() and sys.stdout.isatty()


def _pick_cast_suggestions(suggestions: list[dict[str, object]], title: str) -> list[dict[str, object]]:
    if not suggestions:
        return []
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(json.dumps(suggestions, indent=2))
        print("No interactive terminal detected; rerun with --apply to accept all suggestions.")
        return []
    selected = set()
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
                plays = f" as {item.get('plays')}" if item.get("plays") else ""
                line = f"{marker} {item.get('kind', 'actor')}: {item.get('person')} ({item.get('display_name', '')}){plays}"
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


def _extract_json_array(text: str) -> list[dict[str, object]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("[")
    if start == -1:
        raise ValueError("AI cast suggestion did not contain a JSON array.")
    try:
        data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError:
        data = _salvage_json_objects(cleaned[start:])
    if not isinstance(data, list):
        raise ValueError("AI cast suggestion must be a JSON array.")
    result = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Every cast suggestion must be an object.")
        result.append(item)
    return result


def _salvage_json_objects(text: str) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    depth = 0
    start: int | None = None
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    item = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    start = None
                    continue
                if isinstance(item, dict):
                    objects.append(item)
                start = None
    if not objects:
        raise ValueError("AI cast suggestion did not contain any complete JSON objects.")
    return objects


def _normalize_plays(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def cmd_episode_new(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode = ensure_episode(vault, args.episode_id)
    print(f"Created episode: {episode.name}")
    return 0


def cmd_episode_list(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    for episode in list_episodes(vault):
        print(episode)
    return 0


def cmd_episode_show(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    episode = ensure_episode(vault, args.episode_id)
    meta = read_json(episode / "meta.json", {})
    if args.json:
        print(json.dumps(meta, indent=2, sort_keys=True))
        return 0
    print(f"Episode: {args.episode_id}")
    print(f"Status: {meta.get('status', 'created')}")
    print(f"Completed phases: {', '.join(meta.get('completed_phases', [])) or 'none'}")
    overrides = meta.get("cast_overrides", [])
    print(f"Cast overrides: {len(overrides)}")
    for item in overrides:
        plays = f" as {item.get('plays')}" if item.get("plays") else ""
        print(f"  {item.get('kind', 'actor')}: {item.get('person')}{plays}")
    print("")
    print(_format_current_cast(vault, args.episode_id).rstrip())
    print("")
    print(_format_current_arcs(vault, args.episode_id).rstrip())
    return 0


def cmd_episode_fork(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    target = args.target_id or f"{args.episode_id}-fork"
    copy_episode(vault, args.episode_id, target)
    print(f"Forked {args.episode_id} -> {target}")
    return 0


def _write_room_state(vault: Path, status: str, episode_id: str | None = None) -> None:
    state = read_json(vault / ".room" / "state.json", {"schema": 1})
    state["status"] = status
    if episode_id:
        state["current_episode"] = episode_id
    atomic_write_json(vault / ".room" / "state.json", state)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        try:
            return cmd_status(argparse.Namespace(vault=None, json=False))
        except VaultError:
            parser.print_help()
            return 0
    try:
        return int(args.func(args) or 0)
    except VaultError as exc:
        print(f"showbible: {exc}", file=sys.stderr)
        return EXIT_VAULT
    except ProviderError as exc:
        print(f"showbible: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except ValueError as exc:
        print(f"showbible: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"showbible: {exc}", file=sys.stderr)
        return EXIT_GENERIC


if __name__ == "__main__":
    raise SystemExit(main())
