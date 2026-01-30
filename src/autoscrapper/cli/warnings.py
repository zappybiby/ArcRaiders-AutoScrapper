from __future__ import annotations

from typing import Optional

from rich.console import Console

from ..config import (
    UiSettings,
    has_saved_progress,
    load_progress_settings,
    load_ui_settings,
    save_ui_settings,
)
from ..core.item_actions import ITEM_RULES_CUSTOM_PATH


def maybe_warn_default_rules(console: Optional[Console] = None) -> None:
    ui_settings = load_ui_settings()
    if ui_settings.default_rules_warning_shown:
        return
    if ITEM_RULES_CUSTOM_PATH.exists():
        return
    if has_saved_progress(load_progress_settings()):
        return

    message = (
        "Tip: You are using default rules. "
        "Most users will want to set their progress first for better results."
    )
    if console:
        console.print(f"[yellow]{message}[/yellow]")
    else:
        print(message)

    save_ui_settings(UiSettings(default_rules_warning_shown=True))
