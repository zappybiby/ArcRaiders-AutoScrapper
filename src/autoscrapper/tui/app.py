from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Iterable, Optional

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
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
from ..warmup import start_background_warmup, warmup_status

MenuAction = Callable[["MenuScreen"], None]
_SPLASH_MAX_SECONDS = 8.0
_SPLASH_TICK_SECONDS = 0.08
_SPLASH_BAR_WIDTH = 36
_SPLASH_SPINNER = "|/-\\"
_SPLASH_GLITCH = "._-:=+*#"
_SPLASH_TITLE = (
    "    ___        __        _____                                  ",
    "   /   | _____/ /_____  / ___/____________ _____  ____  ___  _____",
    "  / /| |/ ___/ __/ __ \\ \\__ \\/ ___/ ___/ __ `/ __ \\/ __ \\/ _ \\/ ___/",
    " / ___ / /__/ /_/ /_/ /___/ / /__/ /  / /_/ / /_/ / /_/ /  __/ /    ",
    "/_/  |_\\___/\\__/\\____//____/\\___/_/   \\__,_/ .___/ .___/\\___/_/     ",
    "                                           /_/   /_/                 ",
)


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


class StartupSplash(ModalScreen[None]):
    def __init__(self, *, start_screen: str, scan_dry_run: bool) -> None:
        super().__init__()
        self._start_screen = start_screen
        self._scan_dry_run = scan_dry_run
        self._started_at = 0.0
        self._tick = 0
        self._completed = False
        self._timed_out = False
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="startup-shell"):
            yield Static(id="startup-title")
            yield Static(id="startup-status")
            yield Static(id="startup-bar")
            yield Static(
                "Preparing modules, OCR backend, and scanner runtime...",
                id="startup-hint",
            )

    def on_mount(self) -> None:
        start_background_warmup()
        self._started_at = time.monotonic()
        self._render_frame()
        self._timer = self.set_interval(_SPLASH_TICK_SECONDS, self._render_frame)

    def _animated_title(self, *, ready: bool) -> str:
        if ready:
            return "\n".join(_SPLASH_TITLE)

        reveal_budget = self._tick * 16
        glitch_col = (self._tick * 3) % max(len(line) for line in _SPLASH_TITLE)
        rendered: list[str] = []
        for line in _SPLASH_TITLE:
            line_chars: list[str] = []
            for idx, ch in enumerate(line):
                if ch == " ":
                    line_chars.append(" ")
                    continue
                if reveal_budget <= 0:
                    line_chars.append(" ")
                    continue
                if idx == glitch_col and self._tick % 2 == 0:
                    line_chars.append(
                        _SPLASH_GLITCH[(self._tick + idx) % len(_SPLASH_GLITCH)]
                    )
                else:
                    line_chars.append(ch)
                reveal_budget -= 1
            rendered.append("".join(line_chars))
        return "\n".join(rendered)

    def _progress_percent(self, *, ready: bool, elapsed: float) -> int:
        if ready:
            return 100
        return min(95, int(elapsed * 30))

    def _progress_bar(self, percent: int) -> str:
        filled = int(_SPLASH_BAR_WIDTH * (percent / 100.0))
        filled = max(0, min(_SPLASH_BAR_WIDTH, filled))
        return "[" + ("#" * filled) + ("." * (_SPLASH_BAR_WIDTH - filled)) + "]"

    def _render_frame(self) -> None:
        if self._completed:
            return

        status = warmup_status()
        elapsed = time.monotonic() - self._started_at
        ready = status.completed
        if not ready and elapsed >= _SPLASH_MAX_SECONDS:
            ready = True
            self._timed_out = True

        spinner = _SPLASH_SPINNER[self._tick % len(_SPLASH_SPINNER)]
        percent = self._progress_percent(ready=ready, elapsed=elapsed)

        phase = "Initializing..."
        if status.completed and status.failed:
            phase = "Warmup issue detected, continuing safely..."
        elif status.completed:
            phase = "Initialization complete."
        elif self._timed_out:
            phase = "Warmup taking longer than expected, continuing..."

        self.query_one("#startup-title", Static).update(
            self._animated_title(ready=ready)
        )
        self.query_one("#startup-status", Static).update(f"{spinner} {phase}")
        self.query_one("#startup-bar", Static).update(
            f"{self._progress_bar(percent)} {percent:3d}%"
        )

        self._tick += 1
        if ready:
            self._complete()

    def _complete(self) -> None:
        if self._completed:
            return
        self._completed = True
        if self._timer is not None:
            self._timer.pause()
        self.dismiss()
        if self._start_screen == "scan":
            self.app.set_timer(
                0.01,
                lambda: self.app.push_screen(ScanScreen(dry_run=self._scan_dry_run)),
            )


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
                "Review Rules",
                lambda screen: screen.app.push_screen(RulesScreen()),
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

    def action_back(self) -> None:
        # Home is the root screen; Back should be a no-op here.
        return


class AutoScrapperApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "Autoscrapper"
    BINDINGS = [
        Binding("ctrl+g", "main_menu", "Main menu"),
    ]

    def __init__(self, *, start_screen: str = "home", scan_dry_run: bool = False):
        super().__init__()
        self._start_screen = start_screen
        self._scan_dry_run = scan_dry_run

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
        self.push_screen(
            StartupSplash(
                start_screen=self._start_screen,
                scan_dry_run=self._scan_dry_run,
            )
        )

    def action_main_menu(self) -> None:
        if isinstance(self.screen, ScanScreen):
            return
        while not isinstance(self.screen, HomeScreen):
            self.pop_screen()

    def action_back(self) -> None:
        if isinstance(self.screen, ScanScreen):
            return
        if isinstance(self.screen, HomeScreen):
            return
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
            MenuItem("0", "Back", lambda screen: screen.app.pop_screen()),
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
                "2",
                "Review completed quests",
                lambda screen: launch_review_quests(screen.app),
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
            MenuItem("0", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Progress", items, default_key="1")

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
                "Scan pacing + delays",
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
            MenuItem("0", "Back", lambda screen: screen.app.pop_screen()),
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
            MenuItem("0", "Back", lambda screen: screen.app.pop_screen()),
        ]
        return MenuScreen("Maintenance", items, default_key="1")


def run_tui(*, start_screen: str = "home", dry_run: bool = False) -> int:
    if start_screen not in {"home", "scan"}:
        raise ValueError("start_screen must be 'home' or 'scan'")
    app = AutoScrapperApp(start_screen=start_screen, scan_dry_run=dry_run)
    app.run(mouse=True)
    return 0
