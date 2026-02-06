from __future__ import annotations

from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Static


class AppScreen(Screen):
    BINDINGS = []


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
