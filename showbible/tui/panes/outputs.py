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
