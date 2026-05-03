from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .providers import Provider, resolve_provider
from .vault import (
    append_transcript_entry,
    atomic_write_json,
    atomic_write_text,
    ensure_episode,
    episode_meta,
    people,
    read_json,
    write_episode_meta,
)


PHASES = ["pitch", "break", "fast-draft", "room-pass", "polish", "continuity-check"]
PHASE_ARTIFACTS = {
    "pitch": ("pitch.md",),
    "break": ("beats.md",),
    "fast-draft": ("drafts/v1-fast.md",),
    "room-pass": ("drafts/room-pass-notes.md",),
    "polish": ("script.md",),
    "continuity-check": ("callbacks.yaml",),
}


@dataclass(frozen=True)
class Intervention:
    kind: str
    content: str
    voicing: str | None = None


@dataclass(frozen=True)
class RunResult:
    episode_id: str
    completed_phases: list[str]
    skipped_phases: list[str]
    tokens: int
    dollars: float


def parse_speak_as(value: str) -> Intervention:
    if ":" not in value:
        raise ValueError("Expected speak-as value in '<slug>:<text>' form.")
    slug, text = value.split(":", 1)
    slug = slug.strip()
    text = text.strip()
    if not slug or not text:
        raise ValueError("Speak-as requires both a slug and text.")
    return Intervention(kind="speak-as", voicing=slug, content=text)


def run_episode(
    vault: Path,
    episode_id: str,
    provider_name: str | None = None,
    notes: list[str] | None = None,
    speak_as: list[str] | None = None,
    progress: Callable[[str, str, dict[str, Any]], None] | None = None,
) -> RunResult:
    provider = resolve_provider(provider_name)
    episode = ensure_episode(vault, episode_id)
    meta = episode_meta(episode)
    completed = infer_completed_phases(episode)
    meta["completed_phases"] = completed
    meta["status"] = "running"
    write_episode_meta(episode, meta)
    _write_session_state(vault, episode_id, "running", completed)
    _emit_progress(progress, "episode-started", episode_id, {"provider": provider.name, "completed": completed})
    skipped: list[str] = []
    total_tokens = 0
    total_dollars = 0.0

    interventions = [Intervention("note", note) for note in notes or []]
    interventions.extend(parse_speak_as(value) for value in speak_as or [])
    if interventions:
        _write_interventions(episode, meta, interventions)

    for phase in PHASES:
        if phase in completed:
            skipped.append(phase)
            _emit_progress(progress, "skipped", phase, {"completed": completed})
            continue
        meta["current_phase"] = phase
        meta["status"] = "running"
        meta.setdefault("phase_events", []).append({"phase": phase, "event": "started"})
        write_episode_meta(episode, meta)
        _write_session_state(vault, episode_id, "running", completed, phase)
        _emit_progress(progress, "started", phase, {"completed": completed})
        generation = _run_phase(vault, episode, episode_id, phase, provider, meta)
        total_tokens += generation["tokens"]
        total_dollars += generation["dollars"]
        completed.append(phase)
        meta["completed_phases"] = completed
        meta["current_phase"] = phase
        meta["status"] = "running" if phase != PHASES[-1] else "done"
        meta.setdefault("phase_events", []).append({"phase": phase, "event": "completed"})
        write_episode_meta(episode, meta)
        _write_session_state(vault, episode_id, meta["status"], completed, phase)
        _emit_progress(
            progress,
            "completed",
            phase,
            {"completed": completed, "tokens": generation["tokens"], "dollars": generation["dollars"]},
        )

    if completed == PHASES:
        meta["status"] = "done"
        meta["current_phase"] = PHASES[-1]
        write_episode_meta(episode, meta)
    _write_session_state(vault, episode_id, "done", completed)
    _record_cost(vault, episode_id, provider.name, total_tokens, total_dollars)
    _emit_progress(
        progress,
        "episode-completed",
        episode_id,
        {"completed": completed, "tokens": total_tokens, "dollars": total_dollars, "skipped": skipped},
    )
    return RunResult(
        episode_id=episode_id,
        completed_phases=completed,
        skipped_phases=skipped,
        tokens=total_tokens,
        dollars=total_dollars,
    )


def _emit_progress(
    progress: Callable[[str, str, dict[str, Any]], None] | None,
    event: str,
    phase: str,
    payload: dict[str, Any],
) -> None:
    if progress:
        progress(event, phase, payload)


def infer_completed_phases(episode: Path) -> list[str]:
    completed = []
    for phase in PHASES:
        if all(_artifact_ready(episode / artifact) for artifact in PHASE_ARTIFACTS[phase]):
            completed.append(phase)
    return completed


def _artifact_ready(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _write_interventions(episode: Path, meta: dict[str, Any], interventions: list[Intervention]) -> None:
    transcript = episode / "writers-room" / "000-interventions.md"
    existing = meta.setdefault("interventions", [])
    for intervention in interventions:
        record = {"type": intervention.kind, "content": intervention.content}
        if intervention.voicing:
            record["voicing"] = intervention.voicing
        if record in existing:
            continue
        if intervention.kind == "note":
            append_transcript_entry(transcript, "user", "Producer note", intervention.content, intervention=True)
        elif intervention.kind == "speak-as":
            append_transcript_entry(
                transcript,
                "user",
                f"voicing {intervention.voicing}",
                intervention.content,
                intervention=True,
            )
        existing.append(record)
    write_episode_meta(episode, meta)


def _run_phase(vault: Path, episode: Path, episode_id: str, phase: str, provider: Provider, meta: dict[str, Any]) -> dict[str, float]:
    prompt = _phase_prompt(vault, episode, phase, meta)
    generation = provider.generate(phase, episode_id, prompt)
    cast = people(vault)
    speaker = _speaker_for_phase(phase, cast)
    transcript = episode / "writers-room" / _transcript_name(phase)
    append_transcript_entry(transcript, speaker["display_name"], _role_for_phase(phase), generation.text)

    if phase == "pitch":
        atomic_write_text(episode / "pitch.md", generation.text + "\n")
    elif phase == "break":
        atomic_write_text(episode / "beats.md", generation.text + "\n")
    elif phase == "fast-draft":
        atomic_write_text(episode / "drafts" / "v1-fast.md", generation.text + "\n")
    elif phase == "room-pass":
        atomic_write_text(episode / "drafts" / "room-pass-notes.md", generation.text + "\n")
    elif phase == "polish":
        atomic_write_text(episode / "drafts" / "v2-after-room.md", generation.text + "\n")
        atomic_write_text(episode / "script.md", generation.text + "\n")
    elif phase == "continuity-check":
        atomic_write_text(episode / "callbacks.yaml", "schema: 1\ncallbacks: []\n")
        _append_canon(vault, episode_id, generation.text)
    return {"tokens": generation.tokens, "dollars": generation.dollars}


def _phase_prompt(vault: Path, episode: Path, phase: str, meta: dict[str, Any]) -> str:
    notes = []
    pack = vault / "pack.yaml"
    if pack.exists():
        notes.append("Show pack:\n" + pack.read_text(encoding="utf-8"))
    if meta.get("interventions"):
        notes.extend(item.get("content", "") for item in meta["interventions"])
    if phase in {"break", "fast-draft", "polish"} and (episode / "pitch.md").exists():
        notes.append((episode / "pitch.md").read_text(encoding="utf-8"))
    if phase in {"fast-draft", "room-pass", "polish"} and (episode / "beats.md").exists():
        notes.append((episode / "beats.md").read_text(encoding="utf-8"))
    return "\n\n".join(note for note in notes if note)


def _speaker_for_phase(phase: str, cast: list[dict[str, str]]) -> dict[str, str]:
    if not cast:
        return {"slug": "showrunner", "display_name": "Showrunner"}
    if phase in {"pitch", "room-pass", "continuity-check"}:
        return next((person for person in cast if person["slug"] == "showrunner"), cast[0])
    if phase in {"break", "polish"}:
        return next((person for person in cast if person["slug"] == "director"), cast[0])
    if phase == "fast-draft":
        return next((person for person in cast if "writer" in person["slug"]), cast[-1])
    return cast[0]


def _role_for_phase(phase: str) -> str:
    return {
        "pitch": "Showrunner",
        "break": "Director",
        "fast-draft": "Writer",
        "room-pass": "Room pass",
        "polish": "Director",
        "continuity-check": "Lore Keeper",
    }.get(phase, "Agent")


def _transcript_name(phase: str) -> str:
    index = PHASES.index(phase) + 1
    return f"{index:03d}-phase-{phase}.md"


def _append_canon(vault: Path, episode_id: str, text: str) -> None:
    canon = vault / "lore-bible" / "canon.md"
    existing = canon.read_text(encoding="utf-8") if canon.exists() else "# Canon\n\n## Facts\n\n"
    entry = f"\n- **{episode_id} continuity check** - {text.strip()}\n"
    atomic_write_text(canon, existing.rstrip() + entry)


def _write_session_state(
    vault: Path,
    episode_id: str,
    status: str,
    completed: list[str],
    current_phase: str | None = None,
) -> None:
    payload = {
        "schema": 1,
        "status": status,
        "current_episode": episode_id,
        "current_phase": current_phase,
        "completed_phases": completed,
    }
    atomic_write_json(vault / ".room" / "state.json", payload)
    atomic_write_json(vault / ".room" / "sessions" / f"{episode_id}.json", payload)


def _record_cost(vault: Path, episode_id: str, provider: str, tokens: int, dollars: float) -> None:
    path = vault / ".room" / "costs.json"
    costs = read_json(path, {"episodes": {}, "total_tokens": 0, "total_dollars": 0.0})
    previous = costs.setdefault("episodes", {}).get(episode_id, {"tokens": 0, "dollars": 0.0})
    delta_tokens = max(0, tokens)
    delta_dollars = max(0.0, dollars)
    costs["episodes"][episode_id] = {
        "provider": provider,
        "tokens": previous.get("tokens", 0) + delta_tokens,
        "dollars": round(previous.get("dollars", 0.0) + delta_dollars, 6),
    }
    costs["total_tokens"] = sum(item.get("tokens", 0) for item in costs["episodes"].values())
    costs["total_dollars"] = round(sum(item.get("dollars", 0.0) for item in costs["episodes"].values()), 6)
    atomic_write_json(path, costs)
