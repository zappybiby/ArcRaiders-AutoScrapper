from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Static

from .common import AppScreen, MessageScreen
from ..config import ProgressSettings, save_progress_settings
from ..core.item_actions import ITEM_RULES_CUSTOM_PATH
from ..progress.data_update import DownloadError, update_data_snapshot


class UpdateSnapshotScreen(AppScreen):
    DEFAULT_CSS = """
    UpdateSnapshotScreen {
        padding: 1 2;
    }

    #update-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Update Game Data Snapshot", classes="menu-title")
        yield Static("Fetching latest item + quest data...", id="update-status")
        with Horizontal(id="update-actions"):
            yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self._run_update()

    def _run_update(self) -> None:
        status = self.query_one("#update-status", Static)
        try:
            metadata = update_data_snapshot()
        except DownloadError as exc:
            status.update(f"Download failed: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            status.update(f"Update failed: {exc}")
            return

        summary = (
            f"Update complete.\nItems: {metadata.get('itemCount', 0)}\n"
            f"Quests: {metadata.get('questCount', 0)}\n"
            f"Last updated: {metadata.get('lastUpdated', 'unknown')}"
        )
        status.update(summary)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()


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
            ITEM_RULES_CUSTOM_PATH.unlink(missing_ok=True)
            self.app.pop_screen()
            self.app.push_screen(
                MessageScreen("Custom rules removed. Defaults restored.")
            )
