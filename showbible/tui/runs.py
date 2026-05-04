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
