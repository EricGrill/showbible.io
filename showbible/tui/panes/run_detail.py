from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

from showbible.engine import PHASES
from showbible.tui.panes.base import BasePane


class RunDetailPane(BasePane):
    PANE_TITLE = "Run Detail"

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
