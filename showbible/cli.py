from __future__ import annotations

import argparse
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="showbible", description="Local-first AI writers room framework.")
    sub = parser.add_subparsers(dest="command")

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

    lore = sub.add_parser("lore", help="print canon lore")
    add_vault_flag(lore)
    lore.set_defaults(func=cmd_lore)

    arcs = sub.add_parser("arcs", help="list arcs")
    add_vault_flag(arcs)
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


def cmd_lore(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    print((vault / "lore-bible" / "canon.md").read_text(encoding="utf-8").rstrip())
    return 0


def cmd_arcs(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    for path in sorted((vault / "arcs").glob("*.md")):
        print(path.name)
    return 0


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
        "Use lowercase kebab-case for person and plays. Do not include prose. "
        f"If episode scope is present, suggest additions or overrides for that episode only.\n\n"
        f"Current pack:\n{pack}{episode_context}"
    )
    suggestion_dir = (vault / "episodes" / episode_id) if episode_id else (vault / "research")
    suggestion_path = suggestion_dir / "cast-suggestions.md"
    raw_path = suggestion_dir / "cast-suggestions-raw.md"
    provider = resolve_provider(args.provider)
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
    atomic_write_text(suggestion_path, f"# Cast Suggestions for {show_name}\n\n```json\n{json.dumps(suggestions, indent=2)}\n```\n")
    if args.apply:
        for item in suggestions:
            slug = str(item.get("person") or slugify(str(item.get("display_name") or "person")))
            display = str(item.get("display_name") or slug.replace("-", " ").title())
            kind = str(item.get("kind") or "actor")
            plays = item.get("plays")
            plays_text = str(plays) if plays else None
            write_person(vault, slug, display, kind, plays_text)
            role = CastRole(kind=kind, person=slug, plays=plays_text)
            if episode_id:
                add_episode_cast_role(vault, episode_id, role)
            else:
                add_cast_role(vault, role)
        print(f"Applied {len(suggestions)} cast suggestion(s) to {'episode ' + episode_id if episode_id else 'show'}.")
    elif args.json:
        print(json.dumps(suggestions, indent=2, sort_keys=True))
    else:
        print(json.dumps(suggestions, indent=2))
        print(f"Saved suggestions: {suggestion_path}")
        print("Apply them with the same command plus --apply.")
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


def _extract_json_array(text: str) -> list[dict[str, object]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("[")
    if start == -1:
        raise ValueError("AI cast suggestion did not contain a JSON array.")
    data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(data, list):
        raise ValueError("AI cast suggestion must be a JSON array.")
    result = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Every cast suggestion must be an object.")
        result.append(item)
    return result


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


def cmd_episode_fork(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    target = args.target_id or f"{args.episode_id}-fork"
    copy_episode(vault, args.episode_id, target)
    print(f"Forked {args.episode_id} -> {target}")
    return 0


def _write_room_state(vault: Path, status: str) -> None:
    state = read_json(vault / ".room" / "state.json", {"schema": 1})
    state["status"] = status
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
