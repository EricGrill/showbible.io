from __future__ import annotations

from typing import Any, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, LoadingIndicator, SelectionList, Static
from textual.widgets.selection_list import Selection
from textual.worker import Worker


class AISuggestScreen(ModalScreen[list[dict] | None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
    ]

    DEFAULT_CSS = """
    AISuggestScreen { align: center middle; }
    AISuggestScreen > Vertical {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        width: 80%;
        height: 70%;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        generator: Callable[[], list[dict[str, Any]]],
        format_row: Callable[[dict[str, Any]], str],
    ) -> None:
        super().__init__()
        self._title = title
        self._generator = generator
        self._format_row = format_row
        self._loading = LoadingIndicator(id="ai-loading")
        self._status = Static(f"Generating {title}…", id="ai-status")
        self._selection: SelectionList | None = None
        self._suggestions: list[dict[str, Any]] = []
        self._error: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="ai-container"):
            yield Label(self._title)
            yield self._status
            yield self._loading

    def on_mount(self) -> None:
        self.run_worker(self._generate, thread=True, exclusive=True)

    def _generate(self) -> list[dict[str, Any]]:
        return self._generator()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.is_finished:
            self._loading.remove()
            if event.worker.error:
                self._status.update(f"Failed: {event.worker.error}")
                container = self.query_one("#ai-container", Vertical)
                container.mount(Button("Close", id="ai-close", variant="primary"))
            else:
                suggestions = event.worker.result or []
                if not suggestions:
                    self._status.update("No suggestions returned.")
                    container = self.query_one("#ai-container", Vertical)
                    container.mount(Button("Close", id="ai-close", variant="primary"))
                    return
                self._suggestions = suggestions
                self._status.update("Select suggestions to apply (space toggles, enter applies):")
                # Use integer indices as values so SelectionList can hash them.
                self._selection = SelectionList(
                    *(Selection(self._format_row(item), idx, initial_state=True) for idx, item in enumerate(suggestions)),
                    id="ai-selection",
                )
                container = self.query_one("#ai-container", Vertical)
                container.mount(self._selection)
                container.mount(Button("Apply", id="ai-apply", variant="primary"))
                container.mount(Button("Cancel", id="ai-cancel"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("ai-cancel", "ai-close"):
            self.dismiss(None)
            return
        if event.button.id == "ai-apply" and self._selection is not None:
            selected_indices = list(self._selection.selected)
            self.dismiss([self._suggestions[i] for i in selected_indices])
