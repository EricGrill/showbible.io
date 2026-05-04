from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class ArcAction(Message):
    action: str  # "add" | "edit" | "delete" | "suggest"
    arc_slug: str | None = None
    episode_id: str | None = None
    beat: str | None = None


class ArcPane(BasePane):
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "suggest", "AI suggest"),
    ]

    def __init__(self) -> None:
        super().__init__(id="arc-pane")
        self._list = OptionList(id="arc-list")
        self._detail = Static("Select an arc beat.", id="arc-detail")
        self._beats: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        self._beats = list(state.arc_beats)
        self._list.clear_options()
        for beat in self._beats:
            self._list.add_option(
                Option(f"[{beat.arc}] {beat.episode} [{beat.status}] {beat.beat}", id=f"{beat.arc}|{beat.episode}|{beat.beat}")
            )
        self._list.add_option(Option("+ Add new beat", id="__add__"))
        self._render_detail()

    def _render_detail(self) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._beats):
            self._detail.update("Add a new beat to any arc.")
            return
        beat = self._beats[idx]
        self._detail.update(
            f"arc: {beat.arc}\n"
            f"episode: {beat.episode}\n"
            f"status: {beat.status}\n"
            f"beat: {beat.beat}\n"
            f"file: arcs/{beat.arc}.md"
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__add__":
            self.action_add()
        event.stop()

    def action_add(self) -> None:
        self.post_message(ArcAction(action="add"))

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._beats):
            beat = self._beats[idx]
            self.post_message(ArcAction(action="edit", arc_slug=beat.arc, episode_id=beat.episode, beat=beat.beat))

    def action_delete(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._beats):
            beat = self._beats[idx]
            self.post_message(ArcAction(action="delete", arc_slug=beat.arc, episode_id=beat.episode, beat=beat.beat))

    def action_suggest(self) -> None:
        idx = self._list.highlighted or 0
        slug = self._beats[idx].arc if idx < len(self._beats) else "season-theme"
        self.post_message(ArcAction(action="suggest", arc_slug=slug))
