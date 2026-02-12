from __future__ import annotations

from dataclasses import replace
from typing import Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Footer, Input, Static

from .common import AppScreen, MessageScreen
from ..config import (
    ScanSettings,
    config_path,
    load_scan_settings,
    reset_scan_settings,
    save_scan_settings,
)
from ..interaction.keybinds import stop_key_label, textual_key_to_stop_key
from ..interaction.ui_windows import SCROLL_ALT_CLICKS_PER_PAGE, SCROLL_CLICKS_PER_PAGE


class CaptureStopKeyScreen(ModalScreen[Optional[str]]):
    DEFAULT_CSS = """
    CaptureStopKeyScreen {
        align: center middle;
    }

    #capture-box {
        width: 72%;
        max-width: 84;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }

    #capture-help {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="capture-box"):
            yield Static("Set stop key", classes="modal-title")
            yield Static("Press any key to set the stop key.")
            yield Static(
                "Modifier-only keys (Ctrl/Alt/Shift) are ignored.",
                id="capture-help",
            )
            yield Button("Cancel", id="cancel")

    def on_key(self, event: events.Key) -> None:
        key_name = textual_key_to_stop_key(event.key, event.character)
        if key_name is None:
            return
        self.dismiss(key_name)
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)


class ScanSettingsScreen(AppScreen):
    BINDINGS = [
        *AppScreen.BINDINGS,
        Binding("tab", "focus_next_field", "Next field", show=False, priority=True),
        Binding(
            "shift+tab",
            "focus_previous_field",
            "Previous field",
            show=False,
            priority=True,
        ),
        Binding(
            "up",
            "focus_previous_field",
            "Previous field",
            show=False,
            priority=True,
        ),
        Binding("down", "focus_next_field", "Next field", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    ScanSettingsScreen {
        padding: 1 2;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }

    .field-row {
        height: auto;
        align: left middle;
        margin: 0;
    }

    .field-label {
        width: 30;
        color: $text-muted;
    }

    .field-input {
        width: 9;
        height: 1;
        padding: 0 1;
    }

    .hint {
        color: $text-muted;
    }

    #screen-actions {
        margin-top: 1;
        height: auto;
    }
    """

    _FOCUS_ORDER: tuple[str, ...] = ()
    TITLE = "Scan Settings"

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_scan_settings()

    def on_mount(self) -> None:
        self._load_into_fields()
        self.action_focus_next_field()

    def _focus_candidates(self) -> list[Widget]:
        candidates: list[Widget] = []
        for widget_id in self._FOCUS_ORDER:
            widget = self.query_one(f"#{widget_id}")
            if getattr(widget, "disabled", False):
                continue
            candidates.append(widget)
        return candidates

    def _move_focus(self, delta: int) -> None:
        candidates = self._focus_candidates()
        if not candidates:
            return

        current = self.focused
        if current in candidates:
            index = (candidates.index(current) + delta) % len(candidates)
        else:
            index = 0 if delta > 0 else len(candidates) - 1

        target = candidates[index]
        target.focus()
        target.scroll_visible(immediate=True)

    def action_focus_next_field(self) -> None:
        self._move_focus(1)

    def action_focus_previous_field(self) -> None:
        self._move_focus(-1)

    def _parse_int_field(
        self, field_id: str, *, label: str, min_value: int
    ) -> Optional[int]:
        raw = self.query_one(field_id, Input).value.strip()
        if not raw.isdigit():
            self.app.push_screen(
                MessageScreen(f"Enter a valid {label} (>= {min_value}).")
            )
            return None
        value = int(raw)
        if value < min_value:
            self.app.push_screen(
                MessageScreen(f"Enter a valid {label} (>= {min_value}).")
            )
            return None
        return value

    def _save_settings(self, settings: ScanSettings) -> None:
        self.settings = settings
        save_scan_settings(settings)
        self.app.push_screen(MessageScreen("Scan settings saved."))

    def _load_into_fields(self) -> None:
        raise NotImplementedError


class ScanControlsScreen(ScanSettingsScreen):
    TITLE = "Scan Controls"
    _FOCUS_ORDER = (
        "set-stop-key",
        "scroll-clicks",
        "scroll-clicks-alt",
        "save",
        "back",
    )
    DEFAULT_CSS = ScanSettingsScreen.DEFAULT_CSS + """
    #stop-key-value {
        width: 14;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._stop_key = self.settings.stop_key

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="menu-title")
        yield Static("Use Tab / Shift+Tab or ↑/↓ to move fields.", classes="hint")

        yield Static("Keyboard", classes="section-title")
        with Horizontal(classes="field-row"):
            yield Static("Stop scan key", classes="field-label")
            yield Static("", id="stop-key-value")
            yield Button("Set key", id="set-stop-key")

        yield Static("Scrolling", classes="section-title")
        with Horizontal(classes="field-row"):
            yield Static("Primary clicks", classes="field-label")
            yield Input(
                id="scroll-clicks",
                placeholder=f"{SCROLL_CLICKS_PER_PAGE}",
                classes="field-input",
            )
        with Horizontal(classes="field-row"):
            yield Static("Alternating clicks", classes="field-label")
            yield Input(
                id="scroll-clicks-alt",
                placeholder=f"{SCROLL_ALT_CLICKS_PER_PAGE}",
                classes="field-input",
            )
        yield Static("Leave blank for alternating = primary + 1.", classes="hint")

        yield Static(Text(f"Config file: {config_path()}", style="dim"), classes="hint")

        with Horizontal(id="screen-actions"):
            yield Button("Save", id="save", variant="primary")
            yield Button("Back", id="back")
        yield Footer()

    def _refresh_stop_key_label(self) -> None:
        self.query_one("#stop-key-value", Static).update(stop_key_label(self._stop_key))

    def _load_into_fields(self) -> None:
        self.settings = load_scan_settings()
        self._stop_key = self.settings.stop_key
        self._refresh_stop_key_label()

        self.query_one("#scroll-clicks", Input).value = (
            ""
            if self.settings.scroll_clicks_per_page is None
            else str(self.settings.scroll_clicks_per_page)
        )
        self.query_one("#scroll-clicks-alt", Input).value = (
            ""
            if self.settings.scroll_clicks_alt_per_page is None
            else str(self.settings.scroll_clicks_alt_per_page)
        )

    def _set_stop_key(self) -> None:
        self.app.push_screen(CaptureStopKeyScreen(), self._on_stop_key_selected)

    def _on_stop_key_selected(self, key_name: Optional[str]) -> None:
        if key_name is None:
            return
        self._stop_key = key_name
        self._refresh_stop_key_label()

    def _save(self) -> None:
        scroll_raw = self.query_one("#scroll-clicks", Input).value.strip()
        scroll_value: Optional[int] = None
        if scroll_raw:
            if not scroll_raw.isdigit() or int(scroll_raw) < 0:
                self.app.push_screen(
                    MessageScreen("Enter a valid scroll click count (>= 0).")
                )
                return
            scroll_value = int(scroll_raw)

        scroll_alt_raw = self.query_one("#scroll-clicks-alt", Input).value.strip()
        scroll_alt_value: Optional[int] = None
        if scroll_alt_raw:
            if not scroll_alt_raw.isdigit() or int(scroll_alt_raw) < 0:
                self.app.push_screen(
                    MessageScreen(
                        "Enter a valid alternating scroll click count (>= 0)."
                    )
                )
                return
            scroll_alt_value = int(scroll_alt_raw)

        updated = replace(
            self.settings,
            scroll_clicks_per_page=scroll_value,
            scroll_clicks_alt_per_page=scroll_alt_value,
            stop_key=self._stop_key,
        )
        self._save_settings(updated)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "save":
            self._save()
        elif button_id == "set-stop-key":
            self._set_stop_key()
        elif button_id == "back":
            self.app.pop_screen()


class ScanDetectionScreen(ScanSettingsScreen):
    TITLE = "Detection & OCR"
    _FOCUS_ORDER = (
        "infobox-retries",
        "infobox-delay",
        "ocr-retries",
        "ocr-delay",
        "save",
        "back",
    )

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="menu-title")
        yield Static("Use Tab / Shift+Tab or ↑/↓ to move fields.", classes="hint")

        with Horizontal(classes="field-row"):
            yield Static("Infobox retries", classes="field-label")
            yield Input(id="infobox-retries", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Static("Infobox retry gap (ms)", classes="field-label")
            yield Input(id="infobox-delay", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Static("OCR retries", classes="field-label")
            yield Input(id="ocr-retries", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Static("OCR retry gap (ms)", classes="field-label")
            yield Input(id="ocr-delay", classes="field-input")

        with Horizontal(id="screen-actions"):
            yield Button("Save", id="save", variant="primary")
            yield Button("Back", id="back")
        yield Footer()

    def _load_into_fields(self) -> None:
        self.settings = load_scan_settings()
        self.query_one("#infobox-retries", Input).value = str(
            self.settings.infobox_retries
        )
        self.query_one("#infobox-delay", Input).value = str(
            self.settings.infobox_retry_interval_ms
        )
        self.query_one("#ocr-retries", Input).value = str(
            self.settings.ocr_unreadable_retries
        )
        self.query_one("#ocr-delay", Input).value = str(
            self.settings.ocr_retry_interval_ms
        )

    def _save(self) -> None:
        infobox_retries = self._parse_int_field(
            "#infobox-retries",
            label="infobox retry count",
            min_value=1,
        )
        if infobox_retries is None:
            return

        infobox_delay = self._parse_int_field(
            "#infobox-delay",
            label="infobox retry gap (ms)",
            min_value=0,
        )
        if infobox_delay is None:
            return

        ocr_retries = self._parse_int_field(
            "#ocr-retries",
            label="OCR retry count",
            min_value=0,
        )
        if ocr_retries is None:
            return

        ocr_delay = self._parse_int_field(
            "#ocr-delay",
            label="OCR retry gap (ms)",
            min_value=0,
        )
        if ocr_delay is None:
            return

        updated = replace(
            self.settings,
            infobox_retries=infobox_retries,
            infobox_retry_interval_ms=infobox_delay,
            ocr_unreadable_retries=ocr_retries,
            ocr_retry_interval_ms=ocr_delay,
        )
        self._save_settings(updated)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._save()
        elif event.button.id == "back":
            self.app.pop_screen()


class ScanTimingScreen(ScanSettingsScreen):
    TITLE = "Scan Pacing"
    _FOCUS_ORDER = (
        "action-delay",
        "click-gap",
        "item-infobox-delay",
        "post-delay",
        "save",
        "back",
    )

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="menu-title")
        yield Static("Use Tab / Shift+Tab or ↑/↓ to move fields.", classes="hint")

        with Horizontal(classes="field-row"):
            yield Static("Base input pause (ms)", classes="field-label")
            yield Input(id="action-delay", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Static("Cell infobox L->R gap (ms)", classes="field-label")
            yield Input(id="click-gap", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Static("Item infobox settle gap (ms)", classes="field-label")
            yield Input(id="item-infobox-delay", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Static("Post sell/recycle (ms)", classes="field-label")
            yield Input(id="post-delay", classes="field-input")

        with Horizontal(id="screen-actions"):
            yield Button("Save", id="save", variant="primary")
            yield Button("Back", id="back")
        yield Footer()

    def _load_into_fields(self) -> None:
        self.settings = load_scan_settings()
        self.query_one("#action-delay", Input).value = str(
            self.settings.input_action_delay_ms
        )
        self.query_one("#click-gap", Input).value = str(
            self.settings.cell_infobox_left_right_click_gap_ms
        )
        self.query_one("#item-infobox-delay", Input).value = str(
            self.settings.item_infobox_settle_delay_ms
        )
        self.query_one("#post-delay", Input).value = str(
            self.settings.post_sell_recycle_delay_ms
        )

    def _save(self) -> None:
        action_delay = self._parse_int_field(
            "#action-delay",
            label="base input pause (ms)",
            min_value=0,
        )
        if action_delay is None:
            return

        click_gap = self._parse_int_field(
            "#click-gap",
            label="cell left-to-right click gap (ms)",
            min_value=0,
        )
        if click_gap is None:
            return

        item_infobox_delay = self._parse_int_field(
            "#item-infobox-delay",
            label="item infobox settle gap (ms)",
            min_value=0,
        )
        if item_infobox_delay is None:
            return

        post_delay = self._parse_int_field(
            "#post-delay",
            label="post sell/recycle delay (ms)",
            min_value=0,
        )
        if post_delay is None:
            return

        updated = replace(
            self.settings,
            input_action_delay_ms=action_delay,
            cell_infobox_left_right_click_gap_ms=click_gap,
            item_infobox_settle_delay_ms=item_infobox_delay,
            post_sell_recycle_delay_ms=post_delay,
        )
        self._save_settings(updated)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._save()
        elif event.button.id == "back":
            self.app.pop_screen()


class ScanDiagnosticsScreen(ScanSettingsScreen):
    TITLE = "Diagnostics"
    _FOCUS_ORDER = ("debug-ocr", "profile-timing", "save", "back")

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="menu-title")
        yield Static("Use Tab / Shift+Tab or ↑/↓ to move fields.", classes="hint")

        with Horizontal(classes="field-row"):
            yield Static("Debug OCR", classes="field-label")
            yield Checkbox(id="debug-ocr")
        with Horizontal(classes="field-row"):
            yield Static("Profile timing", classes="field-label")
            yield Checkbox(id="profile-timing")

        with Horizontal(id="screen-actions"):
            yield Button("Save", id="save", variant="primary")
            yield Button("Back", id="back")
        yield Footer()

    def _load_into_fields(self) -> None:
        self.settings = load_scan_settings()
        self.query_one("#debug-ocr", Checkbox).value = self.settings.debug_ocr
        self.query_one("#profile-timing", Checkbox).value = self.settings.profile

    def _save(self) -> None:
        updated = replace(
            self.settings,
            debug_ocr=self.query_one("#debug-ocr", Checkbox).value,
            profile=self.query_one("#profile-timing", Checkbox).value,
        )
        self._save_settings(updated)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._save()
        elif event.button.id == "back":
            self.app.pop_screen()


class ResetScanSettingsScreen(AppScreen):
    DEFAULT_CSS = """
    ResetScanSettingsScreen {
        padding: 1 2;
    }

    #scan-reset-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Reset Scan Settings", classes="menu-title")
        yield Static(
            "This restores all scan settings to defaults. Are you sure?",
            classes="hint",
        )
        with Horizontal(id="scan-reset-actions"):
            yield Button("Cancel", id="cancel")
            yield Button("Reset", id="reset", variant="warning")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "reset":
            reset_scan_settings()
            self.app.pop_screen()
            self.app.push_screen(MessageScreen("Scan settings reset to defaults."))
