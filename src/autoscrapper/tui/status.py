from __future__ import annotations

from datetime import datetime

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..config import has_saved_progress, load_progress_settings
from ..items.rules_store import load_rules, using_custom_rules
from ..progress.data_loader import load_game_data


def _format_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return raw

    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%MZ")


def _format_rules_status() -> str:
    status = "Custom" if using_custom_rules() else "Default"
    payload = load_rules()
    generated_at = payload.get("metadata", {}).get("generatedAt")
    generated_at = _format_timestamp(generated_at)
    if generated_at:
        return f"{status} (generated {generated_at})"
    return status


def _format_progress_status() -> str:
    settings = load_progress_settings()
    if not has_saved_progress(settings):
        return "Not set"
    last_updated = _format_timestamp(settings.last_updated) or "unknown"
    return (
        f"Saved (active {len(settings.active_quests)}, "
        f"completed {len(settings.completed_quests)}, "
        f"workshops {len(settings.hideout_levels)}, "
        f"updated {last_updated})"
    )


def _format_snapshot_status() -> str:
    try:
        game_data = load_game_data()
    except FileNotFoundError:
        return "Missing"
    last_updated = game_data.metadata.get("lastUpdated", "unknown")
    return _format_timestamp(last_updated) or str(last_updated)


def has_progress() -> bool:
    settings = load_progress_settings()
    return has_saved_progress(settings)


def build_status_panel() -> Panel:
    status_table = Table.grid(padding=(0, 1))
    status_table.add_column(justify="right", style="bold")
    status_table.add_column()
    status_table.add_row("Rules", _format_rules_status())
    status_table.add_row("Progress", _format_progress_status())
    status_table.add_row("Game data", _format_snapshot_status())

    tip: Text | None = None
    if not has_progress():
        tip = Text(
            "First run: generate a personalized rule list from your quests and workshop level.",
            style="dim",
        )

    body = (status_table, tip) if tip else (status_table,)
    return Panel(
        Group(*body),
        title=Text("Autoscrapper", style="bold cyan"),
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
