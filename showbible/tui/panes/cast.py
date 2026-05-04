from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class CastAction(Message):
    action: str  # "add" | "edit" | "delete" | "suggest"
    person_slug: str | None = None


class CastPane(BasePane):
    PANE_TITLE = "Cast"
    ACTION_HINTS = "[a] add  [e] edit  [d] delete  [s] AI suggest"
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "suggest", "AI suggest"),
    ]

    def __init__(self) -> None:
        super().__init__(id="cast-pane")
        self._list = OptionList(id="cast-list")
        self._detail = Static("Select a cast member.", id="cast-detail")
        self._roles: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        from showbible.vault import people, episode_cast_roles
        self._roles = list(state.cast)
        people_by_slug = {p["slug"]: p for p in people(state.vault)}
        episode_overrides = {r.person for r in episode_cast_roles(state.vault, state.current_episode)}
        self._list.clear_options()
        for role in self._roles:
            tag = "[ep]" if role.person in episode_overrides else "[sh]"
            display = people_by_slug.get(role.person, {}).get("display_name", role.person)
            self._list.add_option(Option(f"{tag} {role.kind}: {display}", id=role.person))
        self._list.add_option(Option("+ Add new cast member", id="__add__"))
        self._render_detail(state)

    def _render_detail(self, state) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._roles):
            self._detail.update("Select a cast member or + Add.")
            return
        role = self._roles[idx]
        self._detail.update(
            f"kind: {role.kind}\n"
            f"person: {role.person}\n"
            f"plays: {role.plays or '-'}\n"
            f"file: people/{role.person}.md"
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail(self.app.state)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__add__":
            self.action_add()
        event.stop()

    def action_add(self) -> None:
        self.post_message(CastAction(action="add"))

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._roles):
            self.post_message(CastAction(action="edit", person_slug=self._roles[idx].person))

    def action_delete(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._roles):
            self.post_message(CastAction(action="delete", person_slug=self._roles[idx].person))

    def action_suggest(self) -> None:
        self.post_message(CastAction(action="suggest"))
