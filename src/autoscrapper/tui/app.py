from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from .common import AppScreen
from .maintenance import ResetProgressScreen, ResetRulesScreen, UpdateSnapshotScreen
from .progress import (
    launch_edit_workshops,
    launch_generate_rules,
    launch_progress_wizard,
    launch_review_quests,
)
from .rules import RulesScreen
from .scan import ScanScreen
from .settings import (
    ResetScanSettingsScreen,
    ScanControlsScreen,
    ScanDetectionScreen,
    ScanDiagnosticsScreen,
    ScanTimingScreen,
)
from .status import build_status_panel, has_progress

MenuAction = Callable[["MenuScreen"], None]


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    action: MenuAction


class StatusPanel(Static):
    def refresh_status(self) -> None:
        self.update(build_status_panel())

    def on_mount(self) -> None:
        self.refresh_status()


class MenuScreen(AppScreen):
    def __init__(
        self,
        title: str,
        items: Iterable[MenuItem],
        *,
        default_key: str,
        recommended_key: Optional[str] = None,
        show_status: bool = False,
    ) -> None:
        super().__init__()
        self.title = title
        self.items = list(items)
        self.default_key = default_key
        self.recommended_key = recommended_key
        self.show_status = show_status
        self._actions: dict[str, MenuItem] = {}
        self._keys: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-root"):
            if self.show_status:
                yield StatusPanel(id="status")
            yield Static(self.title, classes="menu-title")
            yield OptionList(id="menu")
        yield Footer()

    def on_mount(self) -> None:
        self._render_menu()
        self._focus_menu()

    def on_screen_resume(self, _event: events.ScreenResume) -> None:
        if self.show_status:
            status = self.query_one(StatusPanel)
            status.refresh_status()
        self._render_menu()
        self._focus_menu()

    def _focus_menu(self) -> None:
        menu = self.query_one(OptionList)
        menu.focus()

    def _render_menu(self) -> None:
        self._actions = {item.key: item for item in self.items}
        self._keys = [item.key for item in self.items]
        menu = self.query_one(OptionList)
        menu.set_options([self._build_option(item) for item in self.items])
        self._highlight_default()

    def _build_option(self, item: MenuItem) -> Option:
        is_recommended = self.recommended_key and item.key == self.recommended_key
        text = Text.assemble((item.key, "bold cyan"), " ")
        if is_recommended:
            text.append(item.label, style="bold #f59e0b")
        else:
            text.append(item.label)
        return Option(text, id=item.key)

    def _highlight_default(self) -> None:
        menu = self.query_one(OptionList)
        try:
            index = self._keys.index(self.default_key)
        except ValueError:
            index = 0
        menu.highlighted = index

    def on_key(self, event: events.Key) -> None:
        if event.key in {"escape"}:
            if "b" in self._actions:
                self._select_key("b")
                event.stop()
                return
        if event.key.isalnum():
            key = event.key.lower()
            if key in self._actions:
                self._select_key(key)
                event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option_id
        if option_id and option_id in self._actions:
            self._actions[option_id].action(self)

    def _select_key(self, key: str) -> None:
        if key not in self._actions:
            return
        menu = self.query_one(OptionList)
        try:
            index = self._keys.index(key)
        except ValueError:
            return
        menu.highlighted = index
        menu.action_select()


class HomeScreen(MenuScreen):
    def __init__(self) -> None:
        super().__init__(
            "Main menu",
            [],
            default_key="1",
            recommended_key=None,
            show_status=True,
        )

    def _refresh_items(self) -> None:
        recommended = "2" if not has_progress() else "1"
        self.default_key = recommended
        self.recommended_key = recommended
        self.items = [
            MenuItem(
                "1",
                "Scan",
                lambda screen: screen.app.push_screen(screen.app._scan_menu()),
            ),
            MenuItem(
                "2",
                "Generate Personalized Rule List (Quests / Workshop Level)",
                lambda screen: screen.app.push_screen(screen.app._progress_menu()),
            ),
            MenuItem(
                "3",
                "Rules",
                lambda screen: screen.app.push_screen(screen.app._rules_menu()),
            ),
            MenuItem(
                "4",
                "Settings",
                lambda screen: screen.app.push_screen(screen.app._settings_menu()),
            ),
            MenuItem(
                "5",
                "Maintenance",
                lambda screen: screen.app.push_screen(screen.app._maintenance_menu()),
            ),
            MenuItem("q", "Quit", lambda screen: screen.app.exit()),
        ]

    def on_mount(self) -> None:
        self._refresh_items()
        super().on_mount()

    def on_screen_resume(self, event: events.ScreenResume) -> None:
        self._refresh_items()
        super().on_screen_resume(event)


class AutoScrapperApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "Autoscrapper"

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    def action_main_menu(self) -> None:
        if isinstance(self.screen, ScanScreen):
            return
        while not isinstance(self.screen, HomeScreen):
            self.pop_screen()

    def _scan_menu(self) -> MenuScreen:
        items = [
            MenuItem(
                "1",
                "Scan now",
                lambda screen: screen.app.push_screen(ScanScreen(dry_run=False)),
            ),
            MenuItem(
                "2",
                "Dry run (no clicks)",
                lambda screen: screen.app.push_screen(ScanScreen(dry_run=True)),
            ),
            MenuItem("b", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Scan", items, default_key="1")

    def _progress_menu(self) -> MenuScreen:
        items = [
            MenuItem(
                "1",
                "Set up / update progress",
                lambda screen: launch_progress_wizard(screen.app),
            ),
            MenuItem(
                "2", "Review quests", lambda screen: launch_review_quests(screen.app)
            ),
            MenuItem(
                "3",
                "Edit workshop levels",
                lambda screen: launch_edit_workshops(screen.app),
            ),
            MenuItem(
                "4",
                "Update rules from saved progress",
                lambda screen: launch_generate_rules(screen.app),
            ),
            MenuItem("b", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Progress", items, default_key="1")

    def _rules_menu(self) -> MenuScreen:
        items = [
            MenuItem(
                "1",
                "Review / edit rules",
                lambda screen: screen.app.push_screen(RulesScreen()),
            ),
            MenuItem("b", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Rules", items, default_key="1")

    def _settings_menu(self) -> MenuScreen:
        items = [
            MenuItem(
                "1",
                "Keyboard + scrolling",
                lambda screen: screen.app.push_screen(ScanControlsScreen()),
            ),
            MenuItem(
                "2",
                "Detection + OCR retries",
                lambda screen: screen.app.push_screen(ScanDetectionScreen()),
            ),
            MenuItem(
                "3",
                "Timing delays",
                lambda screen: screen.app.push_screen(ScanTimingScreen()),
            ),
            MenuItem(
                "4",
                "Diagnostics",
                lambda screen: screen.app.push_screen(ScanDiagnosticsScreen()),
            ),
            MenuItem(
                "5",
                "Reset scan settings to defaults",
                lambda screen: screen.app.push_screen(ResetScanSettingsScreen()),
            ),
            MenuItem("b", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Settings", items, default_key="1")

    def _maintenance_menu(self) -> MenuScreen:
        items = [
            MenuItem(
                "1",
                "Update game data snapshot",
                lambda screen: screen.app.push_screen(UpdateSnapshotScreen()),
            ),
            MenuItem(
                "2",
                "Reset saved progress",
                lambda screen: screen.app.push_screen(ResetProgressScreen()),
            ),
            MenuItem(
                "3",
                "Reset rules to default",
                lambda screen: screen.app.push_screen(ResetRulesScreen()),
            ),
            MenuItem("b", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Maintenance", items, default_key="1")


def run_tui() -> int:
    app = AutoScrapperApp()
    app.run(mouse=True)
    return 0
