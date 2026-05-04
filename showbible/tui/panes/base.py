from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Static


class BasePane(Vertical):
    DEFAULT_CSS = """
    BasePane { height: 1fr; }
    BasePane #pane-title { height: 1; padding: 0 1; background: $accent 20%; color: $accent; text-style: bold; }
    BasePane #pane-body { height: 1fr; }
    BasePane #pane-body > Vertical { width: 50%; padding: 0 1; }
    BasePane #pane-list { border-right: solid $accent; }
    """

    PANE_TITLE: str = ""
    ACTION_HINTS: str = ""

    def _title_line(self) -> str:
        if self.ACTION_HINTS:
            return f"{self.PANE_TITLE}  ·  {self.ACTION_HINTS}"
        return self.PANE_TITLE

    def compose(self):
        yield Static(self._title_line(), id="pane-title")
        with Horizontal(id="pane-body"):
            with Vertical(id="pane-list"):
                yield from self.compose_list()
            with Vertical(id="pane-detail"):
                yield from self.compose_detail()

    def compose_list(self):
        yield Static("(empty)", id="pane-list-empty")

    def compose_detail(self):
        yield Static("Select an item.", id="pane-detail-empty")

    def refresh_from_state(self, state) -> None:
        """Override in subclasses to repopulate from AppState."""
