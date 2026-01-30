from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..config import (
    ProgressSettings,
    has_saved_progress,
    load_progress_settings,
    save_progress_settings,
)
from ..core.item_actions import ITEM_RULES_CUSTOM_PATH
from ..items.rules_cli import load_rules, using_custom_rules
from ..progress.data_loader import load_game_data
from . import config as config_cli
from . import scan as scan_cli
from .progress_flow import (
    edit_saved_workshops,
    generate_rules_from_saved_progress,
    review_saved_quests,
    run_progress_wizard,
    run_update_data,
)
from ..items.rules_viewer import run_rules_viewer
from .warnings import maybe_warn_default_rules


def _format_rules_status() -> str:
    status = "Custom" if using_custom_rules() else "Default"
    payload = load_rules()
    generated_at = payload.get("metadata", {}).get("generatedAt")
    if generated_at:
        return f"{status} (generated {generated_at})"
    return status


def _format_progress_status(settings: ProgressSettings) -> str:
    if not has_saved_progress(settings):
        return "Not set"
    last_updated = settings.last_updated or "unknown"
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
    return last_updated


def show_home_menu(console: Optional[Console] = None) -> int:
    console = console or Console()

    actions = {
        "1": ("Scan inventory now", lambda: scan_cli.main([])),
        "2": ("Dry run scan (no clicks)", lambda: scan_cli.main(["--dry-run"])),
        "3": ("Set up / update progress", lambda: run_progress_wizard(console)),
        "4": (
            "Regenerate rules from saved progress",
            lambda: generate_rules_from_saved_progress(console),
        ),
        "5": ("Review quests", lambda: review_saved_quests(console)),
        "6": ("Edit workshop levels", lambda: edit_saved_workshops(console)),
        "7": ("Review / edit rules", lambda: run_rules_viewer(console)),
        "8": ("Scan configuration", lambda: config_cli.main([])),
        "9": ("Update game data snapshot", lambda: run_update_data(console)),
        "10": (
            "Reset saved progress",
            lambda: _reset_progress(console),
        ),
        "11": ("Reset rules to default", lambda: _reset_rules(console)),
        "q": ("Quit", None),
    }

    while True:
        console.print("\n[bold cyan]Autoscrapper[/bold cyan]")
        status_table = Table(show_header=False, box=None)
        progress_settings = load_progress_settings()
        status_table.add_row("Rules", _format_rules_status())
        status_table.add_row("Progress", _format_progress_status(progress_settings))
        status_table.add_row("Data snapshot", _format_snapshot_status())
        console.print(Panel(status_table, border_style="cyan"))

        menu = Table(show_header=False, box=None)
        for key, (label, _) in actions.items():
            menu.add_row(f"[cyan]{key}[/cyan]", label)
        console.print(menu)

        choice = Prompt.ask("Select an option", default="q")
        if choice in {"q", "quit"}:
            return 0
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        label, handler = actions[choice]
        console.print(f"\n[bold]{label}[/bold]")
        if handler is None:
            return 0
        if choice in {"1", "2"}:
            maybe_warn_default_rules(console)
        handler()


def _reset_progress(console: Console) -> None:
    if Confirm.ask(
        "Reset saved progress? This clears quests + workshop levels.", default=False
    ):
        save_progress_settings(ProgressSettings())
        console.print("[green]Progress reset.[/green]")


def _reset_rules(console: Console) -> None:
    if not ITEM_RULES_CUSTOM_PATH.exists():
        console.print("[yellow]Already using default rules.[/yellow]")
        return
    if Confirm.ask(
        "Reset to default rules? This will delete your custom rules.", default=False
    ):
        ITEM_RULES_CUSTOM_PATH.unlink(missing_ok=True)
        console.print("[green]Custom rules removed. Defaults restored.[/green]")
