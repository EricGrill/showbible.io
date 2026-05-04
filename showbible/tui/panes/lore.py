from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from showbible.tui.panes.base import BasePane


@dataclass
class LoreAction(Message):
    action: str  # "add" | "edit" | "delete" | "suggest"
    fact_text: str | None = None


class LorePane(BasePane):
    PANE_TITLE = "Lore"
    ACTION_HINTS = "[a] add  [e] edit  [d] delete  [s] AI suggest"
    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "suggest", "AI suggest"),
    ]

    def __init__(self) -> None:
        super().__init__(id="lore-pane")
        self._list = OptionList(id="lore-list")
        self._detail = Static("Select a fact.", id="lore-detail")
        self._facts: list = []

    def compose_list(self):
        yield self._list

    def compose_detail(self):
        yield self._detail

    def refresh_from_state(self, state) -> None:
        self._facts = list(state.lore_facts)
        self._list.clear_options()
        for fact in self._facts:
            self._list.add_option(Option(fact.text, id=fact.text))
        self._list.add_option(Option("+ Add new fact", id="__add__"))
        self._render_detail()

    def _render_detail(self) -> None:
        idx = self._list.highlighted or 0
        if idx >= len(self._facts):
            self._detail.update("Add a new canon fact.")
            return
        fact = self._facts[idx]
        self._detail.update(
            f"fact: {fact.text}\n"
            f"source: {fact.source}\n"
            "file: lore-bible/canon.md"
        )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "__add__":
            self.action_add()
        event.stop()

    def action_add(self) -> None:
        self.post_message(LoreAction(action="add"))

    def action_edit(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._facts):
            self.post_message(LoreAction(action="edit", fact_text=self._facts[idx].text))

    def action_delete(self) -> None:
        idx = self._list.highlighted or 0
        if idx < len(self._facts):
            self.post_message(LoreAction(action="delete", fact_text=self._facts[idx].text))

    def action_suggest(self) -> None:
        self.post_message(LoreAction(action="suggest"))
