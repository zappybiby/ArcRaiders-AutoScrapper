from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Static

from .common import AppScreen, MessageScreen
from ..config import ProgressSettings, save_progress_settings
from ..items.rules_store import reset_rules


class ResetProgressScreen(AppScreen):
    DEFAULT_CSS = """
    ResetProgressScreen {
        padding: 1 2;
    }

    #reset-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Reset Saved Progress", classes="menu-title")
        yield Static(
            "This clears saved quests and workshop levels. Are you sure?",
            classes="hint",
        )
        with Horizontal(id="reset-actions"):
            yield Button("Cancel", id="cancel")
            yield Button("Reset", id="reset", variant="warning")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "reset":
            save_progress_settings(ProgressSettings())
            self.app.pop_screen()
            self.app.push_screen(MessageScreen("Progress reset."))


class ResetRulesScreen(AppScreen):
    DEFAULT_CSS = """
    ResetRulesScreen {
        padding: 1 2;
    }

    #rules-reset-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Reset Rules to Default", classes="menu-title")
        yield Static(
            "This deletes your custom rules file. Are you sure?",
            classes="hint",
        )
        with Horizontal(id="rules-reset-actions"):
            yield Button("Cancel", id="cancel")
            yield Button("Reset", id="reset", variant="warning")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "reset":
            reset_rules()
            self.app.pop_screen()
            self.app.push_screen(
                MessageScreen("Custom rules removed. Defaults restored.")
            )
