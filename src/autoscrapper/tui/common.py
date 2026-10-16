from __future__ import annotations

from typing import Optional

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Vertical
from textual.renderables.tint import Tint
from textual.screen import ModalScreen, Screen
from textual.strip import Strip
from textual.widgets import Button, OptionList, SelectionList, Static


class _StripedRows:
    def _get_left_gutter_width(self) -> int:
        return super()._get_left_gutter_width() + 2

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        option_index = next(
            (
                segment.style.meta["option"]
                for segment in strip
                if segment.style and "option" in segment.style.meta
            ),
            None,
        )
        if not isinstance(option_index, int):
            return strip
        highlighted = option_index == self.highlighted
        first_line = highlighted and (
            y == 0
            or not any(
                segment.style and segment.style.meta.get("option") == option_index
                for segment in super().render_line(y - 1)
            )
        )
        row_style = self.get_visual_style(
            "option-list--option",
            *(["option-list--option-highlighted"] if highlighted else []),
        ).rich_style
        rendered_style = next(iter(strip)).style
        row_style += Style(
            bgcolor=rendered_style.bgcolor if rendered_style else None,
            meta={"option": option_index},
        )
        strip = Strip.join(
            [Strip([Segment("› " if first_line else "  ", row_style)], 2), strip]
        )
        if option_index % 2 and not highlighted:
            return Strip(
                Tint.process_segments(
                    strip, Color(255, 255, 255, 0.03), self.app.ansi_theme
                ),
                strip.cell_length,
            )
        return strip


class StripedOptionList(_StripedRows, OptionList):
    pass


class StripedSelectionList(_StripedRows, SelectionList[str]):
    pass


class _RuleList:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.styles.padding = 0
        self.styles.scrollbar_gutter = "stable"

    def on_mouse_move(self, event: events.MouseMove) -> None:
        index = event.style.meta.get("option")
        if (
            event.widget is self
            and isinstance(index, int)
            and 0 <= index < self.option_count
        ):
            self.highlighted = index


class RuleOptionList(_RuleList, StripedOptionList):
    pass


class RuleSelectionList(_RuleList, StripedSelectionList):
    pass


def rule_columns(
    name: str, current: str, other: str, width: int, *, custom: bool = False
) -> Text:
    name_width = max(8, width - 35)
    label = Text(name, style="bold")
    label.truncate(name_width - int(custom), overflow="ellipsis")
    if custom:
        label.append("*")
    label.pad_right(name_width - label.cell_len)
    label.append(f" │ {current:<14} │ {other:<15}", style="")
    return label


class AppScreen(Screen):
    BINDINGS = [Binding("escape,ctrl+b", "back", "Back", priority=True)]

    def action_back(self) -> None:
        self.app.pop_screen()


class MessageScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    MessageScreen {
        align: center middle;
    }

    #message-box {
        width: 70%;
        max-width: 80;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }

    #message-text {
        margin-bottom: 1;
    }
    """

    def __init__(self, message: str, *, title: Optional[str] = None) -> None:
        super().__init__()
        self.message = message
        self.title = title or "Notice"

    def compose(self) -> ComposeResult:
        with Vertical(id="message-box"):
            yield Static(self.title, classes="modal-title")
            yield Static(self.message, id="message-text")
            yield Button("OK", id="ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.dismiss()

    def on_key(self, event: events.Key) -> None:
        if event.key in {"escape", "ctrl+b"}:
            self.dismiss()
            event.stop()


def update_inline_filter(event: events.Key, text: str) -> tuple[str, bool]:
    if event.key == "backspace":
        return (text[:-1] if text else text, True)

    character = event.character
    if (
        character
        and len(character) == 1
        and character.isprintable()
        and not event.key.startswith(("ctrl+", "alt+", "meta+"))
    ):
        return (text + character, True)

    return (text, False)
