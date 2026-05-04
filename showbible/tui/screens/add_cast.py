from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from showbible.tui.widgets.entity_form import EntityForm, FormField


@dataclass
class CastFormResult:
    display_name: str
    kind: str
    plays: str
    scope: str  # "show" | "episode"


class AddCastScreen(ModalScreen[CastFormResult | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddCastScreen { align: center middle; }
    AddCastScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 70;
    }
    """

    def __init__(self, *, title: str = "Add cast member", initial: CastFormResult | None = None) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._form = EntityForm(
            [
                FormField("display_name", "Display name", initial.display_name if initial else ""),
                FormField(
                    "kind",
                    "Kind",
                    initial.kind if initial else "actor",
                    options=["actor", "writer", "showrunner", "director"],
                ),
                FormField("plays", "Plays", initial.plays if initial else ""),
                FormField(
                    "scope",
                    "Scope",
                    initial.scope if initial else "show",
                    options=["show", "episode"],
                ),
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
            if not values["display_name"].strip():
                self.notify("Display name required.", severity="error")
                return
            self.dismiss(
                CastFormResult(
                    display_name=values["display_name"].strip(),
                    kind=values["kind"].strip() or "actor",
                    plays=values["plays"].strip(),
                    scope=values["scope"].strip() or "show",
                )
            )
