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
