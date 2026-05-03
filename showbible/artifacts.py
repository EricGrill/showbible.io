from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .vault import VaultError, atomic_write_text, ensure_episode, episode_meta


@dataclass(frozen=True)
class EpisodeArtifact:
    artifact_id: str
    label: str
    relative_path: str
    editable: bool = True


BASE_ARTIFACTS = (
    EpisodeArtifact("pitch", "Pitch", "pitch.md"),
    EpisodeArtifact("beats", "Beats", "beats.md"),
    EpisodeArtifact("fast-draft", "Fast Draft", "drafts/v1-fast.md"),
    EpisodeArtifact("room-pass-notes", "Room Pass Notes", "drafts/room-pass-notes.md"),
    EpisodeArtifact("polish-draft", "Polish Draft", "drafts/v2-after-room.md"),
    EpisodeArtifact("script", "Script", "script.md"),
    EpisodeArtifact("callbacks", "Callbacks", "callbacks.yaml"),
)


def list_episode_artifacts(vault: Path, episode_id: str) -> list[dict[str, Any]]:
    episode = ensure_episode(vault, episode_id)
    artifacts = [_artifact_payload(episode, artifact) for artifact in BASE_ARTIFACTS]
    room = episode / "writers-room"
    for path in sorted(room.glob("*.md")):
        relative = path.relative_to(episode).as_posix()
        artifacts.append(
            _artifact_payload(
                episode,
                EpisodeArtifact(
                    artifact_id=relative,
                    label=f"Transcript - {path.stem}",
                    relative_path=relative,
                ),
            )
        )
    return artifacts


def read_episode_artifact(vault: Path, episode_id: str, artifact_id: str) -> dict[str, Any]:
    episode = ensure_episode(vault, episode_id)
    return _artifact_payload(episode, _resolve_artifact(episode, artifact_id))


def write_episode_artifact(vault: Path, episode_id: str, artifact_id: str, content: str) -> dict[str, Any]:
    episode = ensure_episode(vault, episode_id)
    artifact = _resolve_artifact(episode, artifact_id)
    if not artifact.editable:
        raise VaultError(f"Artifact is not editable: {artifact_id}")
    path = episode / artifact.relative_path
    atomic_write_text(path, content)
    return _artifact_payload(episode, artifact)


def episode_output_payload(vault: Path, episode_id: str) -> dict[str, Any]:
    episode = ensure_episode(vault, episode_id)
    return {
        "episode": episode_id,
        "meta": episode_meta(episode),
        "artifacts": list_episode_artifacts(vault, episode_id),
    }


def _artifact_payload(episode: Path, artifact: EpisodeArtifact) -> dict[str, Any]:
    path = episode / artifact.relative_path
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "id": artifact.artifact_id,
        "label": artifact.label,
        "path": artifact.relative_path,
        "exists": path.exists(),
        "editable": artifact.editable,
        "content": content,
    }


def _resolve_artifact(episode: Path, artifact_id: str) -> EpisodeArtifact:
    for artifact in BASE_ARTIFACTS:
        if artifact.artifact_id == artifact_id:
            return artifact
    if artifact_id.startswith("writers-room/") and artifact_id.endswith(".md"):
        relative = Path(artifact_id)
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
            raise VaultError(f"Invalid artifact id: {artifact_id}")
        return EpisodeArtifact(
            artifact_id=artifact_id,
            label=f"Transcript - {relative.stem}",
            relative_path=relative.as_posix(),
        )
    raise VaultError(f"Unknown episode artifact: {artifact_id}")
