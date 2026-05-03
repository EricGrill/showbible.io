from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .engine import run_episode
from .providers import ProviderError
from .server import serve, status_payload, transcript_text
from .vault import (
    VaultError,
    atomic_write_json,
    atomic_write_text,
    copy_episode,
    doctor,
    ensure_episode,
    init_vault,
    list_episodes,
    people,
    read_json,
    resolve_vault,
    slugify,
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
    run.add_argument("--provider", default="mock")
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
    cont.add_argument("--provider", default="mock")
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

    cast = sub.add_parser("cast", help="inspect or auto-select cast")
    add_vault_flag(cast)
    cast.add_argument("--auto", action="store_true")
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
    vault = resolve_vault(args.vault)
    cast = people(vault)
    if args.auto:
        print("Auto cast selected:")
    for person in cast:
        print(f"{person['slug']}: {person['display_name']}")
    return 0


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
