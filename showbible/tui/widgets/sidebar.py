from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

NAV_OPTIONS = [
    ("episodes", "Episodes"),
    ("cast", "Cast"),
    ("arc", "Arc"),
    ("lore", "Lore"),
    ("outputs", "Outputs"),
]

COMMAND_OPTIONS = [
    ("run", "Run"),       # label is updated dynamically by ShowBibleApp
    ("snapshot", "Snapshot"),
    ("doctor", "Doctor"),
    ("quit", "Quit"),
]


@dataclass
class SidebarSelection(Message):
    section: str  # "nav" | "command" | "run"
    key: str


class Sidebar(Vertical):
    DEFAULT_CSS = """
    Sidebar {
        width: 28;
        border-right: solid $accent;
        padding: 1;
    }
    Sidebar > Label {
        color: $accent;
        text-style: bold;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="sidebar")
        self._nav = OptionList(
            *(Option(label, id=key) for key, label in NAV_OPTIONS),
            id="sidebar-nav",
        )
        self._command = OptionList(
            *(Option(label, id=key) for key, label in COMMAND_OPTIONS),
            id="sidebar-command",
        )
        self._runs = OptionList(id="sidebar-runs")

    def compose(self):
        yield Label("NAVIGATE")
        yield self._nav
        yield Label("COMMAND")
        yield self._command
        yield Label("ACTIVE RUNS")
        yield self._runs

    def on_mount(self) -> None:
        self._nav.highlighted = 0

    def update_run_label(self, episode_id: str) -> None:
        self._command.replace_option_prompt_at_index(0, f"Run {episode_id}")

    def update_active_runs(self, runs: dict) -> None:
        self._runs.clear_options()
        for run_id, handle in runs.items():
            phase = handle.current_phase or "starting"
            done = len(handle.completed_phases)
            label = f"● {handle.episode_id} ({done}/6 · {phase})"
            if handle.status == "complete":
                label = f"✓ {handle.episode_id} done"
            elif handle.status == "failed":
                label = f"✗ {handle.episode_id} failed"
            self._runs.add_option(Option(label, id=run_id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self._nav:
            self.post_message(SidebarSelection(section="nav", key=event.option.id))
        elif event.option_list is self._command:
            self.post_message(SidebarSelection(section="command", key=event.option.id))
        elif event.option_list is self._runs:
            self.post_message(SidebarSelection(section="run", key=event.option.id))
        event.stop()
