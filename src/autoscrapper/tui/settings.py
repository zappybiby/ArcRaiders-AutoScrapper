from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
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
from ..interaction.ui_windows import SCROLL_CLICKS_PER_PAGE


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


class ScanConfigScreen(AppScreen):
    BINDINGS = [
        *AppScreen.BINDINGS,
        ("up", "focus_previous_field", "Previous field"),
        ("down", "focus_next_field", "Next field"),
    ]

    _FOCUS_ORDER = (
        "set-stop-key",
        "pages-manual",
        "pages-count",
        "scroll-default",
        "scroll-clicks",
        "infobox-retries",
        "infobox-delay",
        "ocr-retries",
        "ocr-delay",
        "action-delay",
        "menu-delay",
        "post-delay",
        "debug-ocr",
        "profile-timing",
        "save",
        "reset",
        "back",
    )

    DEFAULT_CSS = """
    ScanConfigScreen {
        padding: 1 2;
    }

    #config-form {
        height: 1fr;
        padding-right: 1;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }

    .field-row {
        height: auto;
        align: left middle;
        margin: 0 0 1 0;
    }

    .field-label {
        width: 30;
        color: $text-muted;
    }

    #stop-key-value {
        width: 16;
        text-style: bold;
    }

    .hint {
        color: $text-muted;
    }

    .field-input {
        min-width: 10;
    }

    #config-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_scan_settings()
        self._stop_key = self.settings.stop_key

    def compose(self) -> ComposeResult:
        yield Static("Scan Settings", classes="menu-title")
        yield Static("Use ↑/↓ to move between fields.", classes="hint")

        with VerticalScroll(id="config-form"):
            yield Static("Controls", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Stop scan key", classes="field-label")
                yield Static("", id="stop-key-value")
                yield Button("Set key", id="set-stop-key")

            yield Static("Pages", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Manual pages", classes="field-label")
                yield Checkbox(id="pages-manual")
                yield Input(
                    id="pages-count",
                    placeholder="Pages",
                    classes="field-input",
                )

            yield Static("Scrolling", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Use default scroll clicks", classes="field-label")
                yield Checkbox(id="scroll-default")
                yield Input(
                    id="scroll-clicks",
                    placeholder=f"Default ({SCROLL_CLICKS_PER_PAGE})",
                    classes="field-input",
                )

            yield Static("Detection & OCR", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Infobox retries", classes="field-label")
                yield Input(id="infobox-retries", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Infobox retry delay (ms)", classes="field-label")
                yield Input(id="infobox-delay", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("OCR retries (0 disables)", classes="field-label")
                yield Input(id="ocr-retries", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("OCR retry delay (ms)", classes="field-label")
                yield Input(id="ocr-delay", classes="field-input")

            yield Static("Timings", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Action delay (ms)", classes="field-label")
                yield Input(id="action-delay", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Menu appear delay (ms)", classes="field-label")
                yield Input(id="menu-delay", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Post-action delay (ms)", classes="field-label")
                yield Input(id="post-delay", classes="field-input")

            yield Static("Diagnostics", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Debug OCR", classes="field-label")
                yield Checkbox(id="debug-ocr")
            with Horizontal(classes="field-row"):
                yield Static("Profile timing", classes="field-label")
                yield Checkbox(id="profile-timing")

            yield Static(
                Text(f"Config file: {config_path()}", style="dim"),
                classes="hint",
            )

        with Horizontal(id="config-actions"):
            yield Button("Save", id="save", variant="primary")
            yield Button("Reset to defaults", id="reset", variant="warning")
            yield Button("Back", id="back")
        yield Footer()

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

    def _load_into_fields(self) -> None:
        settings = self.settings
        self._stop_key = settings.stop_key
        self._refresh_stop_key_label()

        self.query_one("#pages-manual", Checkbox).value = (
            settings.pages_mode == "manual"
        )
        pages_input = self.query_one("#pages-count", Input)
        pages_input.value = "" if settings.pages is None else str(settings.pages)
        pages_input.disabled = settings.pages_mode != "manual"

        scroll_default = self.query_one("#scroll-default", Checkbox)
        scroll_default.value = settings.scroll_clicks_per_page is None
        scroll_input = self.query_one("#scroll-clicks", Input)
        scroll_input.value = (
            ""
            if settings.scroll_clicks_per_page is None
            else str(settings.scroll_clicks_per_page)
        )
        scroll_input.disabled = scroll_default.value

        self.query_one("#infobox-retries", Input).value = str(settings.infobox_retries)
        self.query_one("#infobox-delay", Input).value = str(
            settings.infobox_retry_delay_ms
        )
        self.query_one("#ocr-retries", Input).value = str(
            settings.ocr_unreadable_retries
        )
        self.query_one("#ocr-delay", Input).value = str(
            settings.ocr_unreadable_retry_delay_ms
        )
        self.query_one("#action-delay", Input).value = str(settings.action_delay_ms)
        self.query_one("#menu-delay", Input).value = str(settings.menu_appear_delay_ms)
        self.query_one("#post-delay", Input).value = str(
            settings.sell_recycle_post_delay_ms
        )
        self.query_one("#debug-ocr", Checkbox).value = settings.debug_ocr
        self.query_one("#profile-timing", Checkbox).value = settings.profile

    def _refresh_stop_key_label(self) -> None:
        self.query_one("#stop-key-value", Static).update(stop_key_label(self._stop_key))

    def _save(self) -> None:
        pages_manual = self.query_one("#pages-manual", Checkbox).value
        pages_input = self.query_one("#pages-count", Input).value.strip()
        pages_mode = "manual" if pages_manual else "auto"
        pages_value = None
        if pages_manual:
            if not pages_input.isdigit() or int(pages_input) < 1:
                self.app.push_screen(
                    MessageScreen("Enter a valid number of pages (>= 1).")
                )
                return
            pages_value = int(pages_input)

        scroll_default = self.query_one("#scroll-default", Checkbox).value
        scroll_input = self.query_one("#scroll-clicks", Input).value.strip()
        scroll_value = None
        if not scroll_default:
            if not scroll_input.isdigit() or int(scroll_input) < 0:
                self.app.push_screen(
                    MessageScreen("Enter a valid scroll click count (>= 0).")
                )
                return
            scroll_value = int(scroll_input)

        infobox_retries = self._parse_int_field(
            "#infobox-retries",
            label="infobox retry count",
            min_value=1,
        )
        if infobox_retries is None:
            return

        infobox_delay = self._parse_int_field(
            "#infobox-delay",
            label="infobox retry delay (ms)",
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
            label="OCR retry delay (ms)",
            min_value=0,
        )
        if ocr_delay is None:
            return

        action_delay = self._parse_int_field(
            "#action-delay",
            label="action delay (ms)",
            min_value=0,
        )
        if action_delay is None:
            return

        menu_delay = self._parse_int_field(
            "#menu-delay",
            label="menu appear delay (ms)",
            min_value=0,
        )
        if menu_delay is None:
            return

        post_delay = self._parse_int_field(
            "#post-delay",
            label="post-action delay (ms)",
            min_value=0,
        )
        if post_delay is None:
            return

        self.settings = ScanSettings(
            pages_mode=pages_mode,
            pages=pages_value,
            scroll_clicks_per_page=scroll_value,
            stop_key=self._stop_key,
            infobox_retries=infobox_retries,
            infobox_retry_delay_ms=infobox_delay,
            ocr_unreadable_retries=ocr_retries,
            ocr_unreadable_retry_delay_ms=ocr_delay,
            action_delay_ms=action_delay,
            menu_appear_delay_ms=menu_delay,
            sell_recycle_post_delay_ms=post_delay,
            debug_ocr=self.query_one("#debug-ocr", Checkbox).value,
            profile=self.query_one("#profile-timing", Checkbox).value,
        )
        save_scan_settings(self.settings)
        self.app.push_screen(MessageScreen("Scan settings saved."))

    def _reset(self) -> None:
        reset_scan_settings()
        self.settings = load_scan_settings()
        self._load_into_fields()
        self.app.push_screen(MessageScreen("Settings reset to defaults."))

    def _set_stop_key(self) -> None:
        self.app.push_screen(CaptureStopKeyScreen(), self._on_stop_key_selected)

    def _on_stop_key_selected(self, key_name: Optional[str]) -> None:
        if key_name is None:
            return
        self._stop_key = key_name
        self._refresh_stop_key_label()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "pages-manual":
            pages_input = self.query_one("#pages-count", Input)
            pages_input.disabled = not event.checkbox.value
            if pages_input.disabled and self.focused is pages_input:
                event.checkbox.focus()
        if event.checkbox.id == "scroll-default":
            scroll_input = self.query_one("#scroll-clicks", Input)
            scroll_input.disabled = event.checkbox.value
            if scroll_input.disabled and self.focused is scroll_input:
                event.checkbox.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "save":
            self._save()
        elif button_id == "reset":
            self._reset()
        elif button_id == "set-stop-key":
            self._set_stop_key()
        elif button_id == "back":
            self.app.pop_screen()
