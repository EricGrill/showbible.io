from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Static

from showbible.tui.runs import RunRegistry
from showbible.tui.state import AppState
from showbible.tui.widgets.sidebar import Sidebar, SidebarSelection


class ShowBibleApp(App):
    CSS = """
    Screen { layout: vertical; }
    #header-bar { height: 1; padding: 0 1; background: $accent 30%; }
    Horizontal#main { height: 1fr; }
    #content { padding: 1 2; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    state: reactive[AppState] = reactive(None, init=False)

    def __init__(self, *, vault: Path, episode_id: str, provider: str) -> None:
        super().__init__()
        self._vault = vault
        self._episode_id = episode_id
        self._provider = provider
        self._run_registry = RunRegistry()
        self.state = AppState.empty(vault=vault, current_episode=episode_id).refreshed_from_disk()

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header-bar")
        with Horizontal(id="main"):
            yield Sidebar()
            yield Static("Select Episodes from the sidebar to begin.", id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self.state = self.state.refreshed_from_disk().with_runs(self._run_registry.snapshot())
        self._update_chrome()

    def _update_chrome(self) -> None:
        self.query_one("#header-bar", Static).update(self._header_text())
        sidebar = self.query_one(Sidebar)
        sidebar.update_run_label(self.state.current_episode)
        sidebar.update_active_runs(self.state.runs)

    def _header_text(self) -> str:
        return (
            f"ShowBible · {self.state.show_name} · vault: {self._vault}"
            f" · {self.state.current_episode}"
        )

    def action_refresh(self) -> None:
        self._tick()

    def on_sidebar_selection(self, message: SidebarSelection) -> None:
        if message.section == "command" and message.key == "quit":
            self.exit(0)
