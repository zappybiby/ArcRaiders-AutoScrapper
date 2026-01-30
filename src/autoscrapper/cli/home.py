from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

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

MenuHandler = Callable[[], object]


def _format_timestamp(value: Optional[str]) -> Optional[str]:
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


def _format_progress_status(settings: ProgressSettings) -> str:
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


def _render_status_panel(console: Console, progress_settings: ProgressSettings) -> None:
    status_table = Table.grid(padding=(0, 1))
    status_table.add_column(justify="right", style="bold")
    status_table.add_column()
    status_table.add_row("Rules", _format_rules_status())
    status_table.add_row("Progress", _format_progress_status(progress_settings))
    status_table.add_row("Game data", _format_snapshot_status())

    tip: Optional[Text] = None
    if not has_saved_progress(progress_settings):
        tip = Text(
            "First run: set up your progress to generate rules for your quests/workshops.",
            style="dim",
        )

    body = Group(status_table, tip) if tip else status_table
    console.print(
        Panel(
            body,
            title=Text("Autoscrapper", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _render_menu_panel(
    title: str,
    actions: dict[str, str],
    *,
    default_key: str,
    border_style: str = "cyan",
) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", width=4)
    table.add_column()

    for key, label in actions.items():
        is_default = key == default_key
        key_style = "bold yellow" if is_default else "bold cyan"
        label_text = Text(label, style="bold" if is_default else "")
        if is_default:
            label_text.append("  (recommended)", style="dim")
        table.add_row(Text(key, style=key_style), label_text)

    return Panel(
        table,
        title=Text(title, style="bold"),
        border_style=border_style,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _prompt_menu_choice(prompt: str, *, default: str) -> str:
    raw = Prompt.ask(prompt, default=default)
    return raw.strip().lower()


def _scan_menu(console: Console) -> None:
    actions: dict[str, tuple[str, Optional[MenuHandler]]] = {
        "1": ("Scan now", lambda: scan_cli.main([])),
        "2": ("Dry run (no clicks)", lambda: scan_cli.main(["--dry-run"])),
        "b": ("Back", None),
    }

    while True:
        console.print()
        console.print(
            _render_menu_panel(
                "Scan",
                {k: v[0] for k, v in actions.items()},
                default_key="1",
            )
        )
        choice = _prompt_menu_choice("Select an option", default="1")
        if choice in {"b", "back", "q", "quit"}:
            return
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        label, handler = actions[choice]
        console.print(f"\n[bold]{label}[/bold]")
        if handler is None:
            return
        maybe_warn_default_rules(console)
        handler()


def _progress_menu(console: Console) -> None:
    actions: dict[str, tuple[str, Optional[MenuHandler]]] = {
        "1": (
            "Set up / update progress (quests + workshops)",
            lambda: run_progress_wizard(console),
        ),
        "2": ("Review quests", lambda: review_saved_quests(console)),
        "3": ("Edit workshop levels", lambda: edit_saved_workshops(console)),
        "4": (
            "Update rules from saved progress",
            lambda: generate_rules_from_saved_progress(console),
        ),
        "b": ("Back", None),
    }

    while True:
        console.print()
        console.print(
            _render_menu_panel(
                "Progress",
                {k: v[0] for k, v in actions.items()},
                default_key="1",
            )
        )
        choice = _prompt_menu_choice("Select an option", default="1")
        if choice in {"b", "back", "q", "quit"}:
            return
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        label, handler = actions[choice]
        console.print(f"\n[bold]{label}[/bold]")
        if handler is None:
            return
        handler()


def _rules_menu(console: Console) -> None:
    actions: dict[str, tuple[str, Optional[MenuHandler]]] = {
        "1": ("Review / edit rules", lambda: run_rules_viewer(console)),
        "b": ("Back", None),
    }

    while True:
        console.print()
        console.print(
            _render_menu_panel(
                "Rules",
                {k: v[0] for k, v in actions.items()},
                default_key="1",
            )
        )
        choice = _prompt_menu_choice("Select an option", default="1")
        if choice in {"b", "back", "q", "quit"}:
            return
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        label, handler = actions[choice]
        console.print(f"\n[bold]{label}[/bold]")
        if handler is None:
            return
        handler()


def _settings_menu(console: Console) -> None:
    actions: dict[str, tuple[str, Optional[MenuHandler]]] = {
        "1": ("Scan configuration", lambda: config_cli.main([])),
        "b": ("Back", None),
    }

    while True:
        console.print()
        console.print(
            _render_menu_panel(
                "Settings",
                {k: v[0] for k, v in actions.items()},
                default_key="1",
            )
        )
        choice = _prompt_menu_choice("Select an option", default="1")
        if choice in {"b", "back", "q", "quit"}:
            return
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        label, handler = actions[choice]
        console.print(f"\n[bold]{label}[/bold]")
        if handler is None:
            return
        handler()


def _maintenance_menu(console: Console) -> None:
    actions: dict[str, tuple[str, Optional[MenuHandler]]] = {
        "1": ("Update game data snapshot", lambda: run_update_data(console)),
        "2": ("Reset saved progress", lambda: _reset_progress(console)),
        "3": ("Reset rules to default", lambda: _reset_rules(console)),
        "b": ("Back", None),
    }

    while True:
        console.print()
        console.print(
            _render_menu_panel(
                "Maintenance",
                {k: v[0] for k, v in actions.items()},
                default_key="1",
                border_style="magenta",
            )
        )
        choice = _prompt_menu_choice("Select an option", default="1")
        if choice in {"b", "back", "q", "quit"}:
            return
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        label, handler = actions[choice]
        console.print(f"\n[bold]{label}[/bold]")
        if handler is None:
            return
        handler()


def show_home_menu(console: Optional[Console] = None) -> int:
    console = console or Console()

    actions: dict[str, tuple[str, Optional[MenuHandler]]] = {
        "1": ("Scan", lambda: _scan_menu(console)),
        "2": ("Progress (quests + workshops)", lambda: _progress_menu(console)),
        "3": ("Rules", lambda: _rules_menu(console)),
        "4": ("Settings", lambda: _settings_menu(console)),
        "5": ("Maintenance", lambda: _maintenance_menu(console)),
        "q": ("Quit", None),
    }

    while True:
        progress_settings = load_progress_settings()

        console.print()
        _render_status_panel(console, progress_settings)

        recommended = "2" if not has_saved_progress(progress_settings) else "1"
        console.print(
            _render_menu_panel(
                "Main menu",
                {k: v[0] for k, v in actions.items()},
                default_key=recommended,
            )
        )

        choice = _prompt_menu_choice("What would you like to do?", default=recommended)
        if choice in {"q", "quit"}:
            return 0
        if choice not in actions:
            console.print("[yellow]Invalid choice.[/yellow]")
            continue

        _label, handler = actions[choice]
        if handler is None:
            return 0
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
