from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Static


class BasePane(Horizontal):
    DEFAULT_CSS = """
    BasePane { height: 1fr; }
    BasePane > Vertical { width: 50%; padding: 0 1; }
    BasePane #pane-list { border-right: solid $accent; }
    """

    def compose(self):
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
