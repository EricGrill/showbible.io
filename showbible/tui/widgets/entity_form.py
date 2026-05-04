from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select


@dataclass
class FormField:
    name: str
    label: str
    default: str = ""
    options: list[str] | None = None  # if set, render a Select instead of Input


class EntityForm(Vertical):
    DEFAULT_CSS = """
    EntityForm { padding: 1 2; height: auto; }
    EntityForm > Horizontal { height: auto; margin-bottom: 1; }
    EntityForm Label { width: 18; }
    EntityForm Input, EntityForm Select { width: 1fr; }
    EntityForm #form-buttons { align-horizontal: right; }
    """

    def __init__(self, fields: list[FormField], submit_label: str = "Save") -> None:
        super().__init__(id="entity-form")
        self._fields = fields
        self._submit_label = submit_label
        self._inputs: dict[str, Input | Select] = {}

    def compose(self):
        for field in self._fields:
            with Horizontal():
                yield Label(field.label)
                if field.options is not None:
                    widget = Select(
                        [(opt, opt) for opt in field.options],
                        value=field.default or field.options[0],
                        id=f"form-{field.name}",
                    )
                else:
                    widget = Input(value=field.default, id=f"form-{field.name}")
                self._inputs[field.name] = widget
                yield widget
        with Horizontal(id="form-buttons"):
            yield Button("Cancel", id="form-cancel")
            yield Button(self._submit_label, id="form-submit", variant="primary")

    def values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, widget in self._inputs.items():
            if isinstance(widget, Input):
                result[name] = widget.value
            elif isinstance(widget, Select):
                result[name] = "" if widget.value is Select.BLANK else str(widget.value)
        return result
