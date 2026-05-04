from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from showbible.tui.widgets.entity_form import EntityForm, FormField


@dataclass
class ArcBeatFormResult:
    arc_slug: str
    episode_id: str
    status: str
    beat: str


class AddArcBeatScreen(ModalScreen[ArcBeatFormResult | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddArcBeatScreen { align: center middle; }
    AddArcBeatScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 70;
    }
    """

    def __init__(
        self,
        *,
        title: str = "Add arc beat",
        initial: ArcBeatFormResult | None = None,
        default_episode: str = "S01E01",
    ) -> None:
        super().__init__()
        self._title = title
        self._initial = initial
        self._form = EntityForm(
            [
                FormField("arc_slug", "Arc", initial.arc_slug if initial else "season-theme"),
                FormField("episode_id", "Episode", initial.episode_id if initial else default_episode),
                FormField(
                    "status",
                    "Status",
                    initial.status if initial else "planned",
                    options=["planned", "in-progress", "done"],
                ),
                FormField("beat", "Beat", initial.beat if initial else ""),
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
            if not values["beat"].strip():
                self.notify("Beat text required.", severity="error")
                return
            self.dismiss(
                ArcBeatFormResult(
                    arc_slug=values["arc_slug"].strip() or "season-theme",
                    episode_id=values["episode_id"].strip() or "S01E01",
                    status=values["status"].strip() or "planned",
                    beat=values["beat"].strip(),
                )
            )
