from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from showbible.tui.widgets.entity_form import EntityForm, FormField


@dataclass
class LoreFactFormResult:
    text: str
    source: str


class AddLoreScreen(ModalScreen[LoreFactFormResult | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddLoreScreen { align: center middle; }
    AddLoreScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 70;
    }
    """

    def __init__(
        self,
        *,
        title: str = "Add canon fact",
        initial: LoreFactFormResult | None = None,
        default_source: str = "manual",
    ) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._form = EntityForm(
            [
                FormField("text", "Fact", initial.text if initial else ""),
                FormField("source", "Source", initial.source if initial else default_source),
            ],
        )

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield self._form

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "form-cancel":
            self.dismiss(None)
            return
        if event.button.id == "form-submit":
            values = self._form.values()
            if not values["text"].strip():
                self.notify("Fact text required.", severity="error")
                return
            self.dismiss(
                LoreFactFormResult(
                    text=values["text"].strip(),
                    source=values["source"].strip() or "manual",
                )
            )
