from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Static

from showbible.tui.panes.arc import ArcPane
from showbible.tui.panes.base import BasePane
from showbible.tui.panes.cast import CastAction, CastPane
from showbible.tui.screens.add_cast import AddCastScreen, CastFormResult
from showbible.tui.screens.ai_suggest import AISuggestScreen
from showbible.tui.screens.confirm import ConfirmScreen
from showbible.tui.panes.episodes import EpisodeSelected, EpisodesPane
from showbible.tui.panes.lore import LorePane
from showbible.tui.panes.outputs import OutputsPane
from showbible.tui.panes.run_detail import RunDetailPane
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

    PANE_FACTORIES = {
        "episodes": EpisodesPane,
        "cast": CastPane,
        "arc": ArcPane,
        "lore": LorePane,
        "outputs": OutputsPane,
    }

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
            with Vertical(id="content"):
                yield EpisodesPane()
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._populate_panes()

    def _tick(self) -> None:
        self.state = self.state.refreshed_from_disk().with_runs(self._run_registry.snapshot())
        self._update_chrome()
        self._populate_panes()

    def _populate_panes(self) -> None:
        for pane in self.query(BasePane):
            pane.refresh_from_state(self.state)

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
        if message.section == "command":
            self._handle_command(message.key)
            return
        if message.section == "nav":
            factory = self.PANE_FACTORIES.get(message.key)
            if factory is not None:
                self._mount_pane(factory())
            return
        if message.section == "run":
            self._mount_pane(RunDetailPane(message.key))

    def _handle_command(self, key: str) -> None:
        if key == "quit":
            self.exit(0)
        elif key == "snapshot":
            from showbible.tui.screens.snapshot import SnapshotScreen
            self.push_screen(SnapshotScreen())
        elif key == "doctor":
            from showbible.tui.screens.doctor import DoctorScreen
            self.push_screen(DoctorScreen())
        elif key == "run":
            self._dispatch_run()

    def _dispatch_run(self) -> None:
        # Replaced in Task 30 (Run worker).
        self.notify("Run dispatch wired in Task 30.")

    def _mount_pane(self, pane) -> None:
        content = self.query_one("#content", Vertical)
        content.remove_children()
        content.mount(pane)
        pane.refresh_from_state(self.state)

    def on_episode_selected(self, message: EpisodeSelected) -> None:
        self.state = self.state.with_episode(message.episode_id)
        self._write_room_state()
        self._update_chrome()
        self._populate_panes()

    def _write_room_state(self) -> None:
        from showbible.cli import _write_room_state
        _write_room_state(self._vault, "planning", episode_id=self.state.current_episode)

    def on_cast_action(self, message: CastAction) -> None:
        from showbible.vault import people

        vault = self.state.vault

        if message.action == "add":
            self.push_screen(
                AddCastScreen(),
                lambda result: self._apply_cast_form(result),
            )
        elif message.action == "edit" and message.person_slug:
            existing = next((r for r in self.state.cast if r.person == message.person_slug), None)
            if existing is None:
                return
            people_by_slug = {p["slug"]: p for p in people(vault)}
            display = people_by_slug.get(existing.person, {}).get("display_name", existing.person)
            self.push_screen(
                AddCastScreen(
                    title="Edit cast member",
                    initial=CastFormResult(
                        display_name=display,
                        kind=existing.kind,
                        plays=existing.plays or "",
                        scope="show",
                    ),
                ),
                lambda result: self._apply_cast_form(result, replacing=existing.person),
            )
        elif message.action == "delete" and message.person_slug:
            self.push_screen(
                ConfirmScreen(f"Delete {message.person_slug}?"),
                lambda confirmed: self._delete_cast_role(message.person_slug, confirmed or False),
            )
        elif message.action == "suggest":
            from showbible.cli import _generate_cast_suggestions
            episode_id = self.state.current_episode
            self.push_screen(
                AISuggestScreen(
                    title="cast suggestions",
                    generator=lambda: _generate_cast_suggestions(vault, episode_id, self._provider, limit=6),
                    format_row=lambda item: f"{item.get('kind', 'actor')}: {item.get('person')} ({item.get('display_name', '')})",
                ),
                lambda picked: self._apply_cast_picked(picked),
            )

    def _apply_cast_form(self, result: CastFormResult | None, *, replacing: str | None = None) -> None:
        if result is None:
            return
        from showbible.vault import (
            CastRole,
            add_cast_role,
            add_episode_cast_role,
            remove_cast_role,
            remove_episode_cast_role,
            slugify,
            write_person,
        )
        slug = slugify(result.display_name)
        write_person(self.state.vault, slug, result.display_name, result.kind, result.plays or None)
        if replacing and replacing != slug:
            remove_cast_role(self.state.vault, replacing)
            remove_episode_cast_role(self.state.vault, self.state.current_episode, replacing)
        role = CastRole(kind=result.kind, person=slug, plays=result.plays or None)
        if result.scope == "episode":
            add_episode_cast_role(self.state.vault, self.state.current_episode, role)
            msg = f"Added {result.kind} {result.display_name} to {self.state.current_episode}."
        else:
            add_cast_role(self.state.vault, role)
            msg = f"Added show {result.kind} {result.display_name}."
        self.state = self.state.with_action(msg).refreshed_from_disk()
        self._populate_panes()

    def _delete_cast_role(self, person_slug: str, confirmed: bool) -> None:
        if not confirmed:
            return
        from showbible.vault import remove_cast_role, remove_episode_cast_role
        remove_cast_role(self.state.vault, person_slug)
        remove_episode_cast_role(self.state.vault, self.state.current_episode, person_slug)
        self.state = self.state.with_action(f"Deleted {person_slug}.").refreshed_from_disk()
        self._populate_panes()

    def _apply_cast_picked(self, picked: list[dict] | None) -> None:
        if not picked:
            return
        from showbible.cli import _apply_cast_suggestions
        _apply_cast_suggestions(self.state.vault, self.state.current_episode, picked)
        self.state = self.state.with_action(f"Applied {len(picked)} cast suggestion(s).").refreshed_from_disk()
        self._populate_panes()
