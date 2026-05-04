from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class DoctorScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
    ]

    DEFAULT_CSS = """
    DoctorScreen { align: center middle; }
    DoctorScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 80%;
        height: 70%;
    }
    """

    def compose(self) -> ComposeResult:
        findings = self.app.state.doctor_findings
        if not findings:
            text = "All clean."
        else:
            text = "\n".join(f"[{f.level}] {f.path}: {f.message}" for f in findings)
        with Vertical():
            yield Label("Doctor")
            with VerticalScroll():
                yield Static(text)
            yield Button("Close", id="doctor-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
