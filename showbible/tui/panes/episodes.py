from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


class EpisodeSelected(Message):
    def __init__(self, episode_id: str) -> None:
        super().__init__()
        self.episode_id = episode_id


class EpisodesPane(BasePane):
    BINDINGS = [
        Binding("n", "new", "New episode"),
    ]

    current_episode: reactive[str] = reactive("S01E01")

    def __init__(self) -> None:
        super().__init__(id="episodes-pane")
        self._list = OptionList(id="episodes-list")
        self._detail = Static("Select an episode.", id="episodes-detail")

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        self._list.clear_options()
        for ep in state.episodes:
            marker = "▶ " if ep == state.current_episode else "  "
            self._list.add_option(Option(f"{marker}{ep}", id=ep))
        self._list.add_option(Option("+ New episode", id="__new__"))
        self.current_episode = state.current_episode
        self._render_detail(state)

    def _render_detail(self, state) -> None:
        from showbible.vault import episode_meta
        ep_dir = state.vault / "episodes" / state.current_episode
        meta = episode_meta(ep_dir) if ep_dir.exists() else {}
        self._detail.update(
            f"episode: {state.current_episode}\n"
            f"status: {meta.get('status', 'created')}\n"
            f"completed phases: {len(meta.get('completed_phases', []))}\n"
            f"cast overrides: {len(meta.get('cast_overrides', []))}"
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__new__":
            self.action_new()
        else:
            self.post_message(EpisodeSelected(event.option.id))
        event.stop()

    def action_new(self) -> None:
        from showbible.cli import _next_episode_id
        from showbible.vault import ensure_episode, list_episodes
        new_id = _next_episode_id(list_episodes(self.app.state.vault))
        ensure_episode(self.app.state.vault, new_id)
        self.post_message(EpisodeSelected(new_id))
