from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class SnapshotScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
    ]

    DEFAULT_CSS = """
    SnapshotScreen { align: center middle; }
    SnapshotScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 90%;
        height: 80%;
    }
    """

    def compose(self) -> ComposeResult:
        from showbible.cli import _workflow_snapshot_text
        snapshot = _workflow_snapshot_text(
            self.app.state.vault,
            self.app.state.current_episode,
            self.app._provider,
        )
        with Vertical():
            yield Label("Workflow snapshot")
            with VerticalScroll():
                yield Static(snapshot)
            yield Button("Close", id="snapshot-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
