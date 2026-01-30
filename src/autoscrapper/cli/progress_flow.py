from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Dict, Iterable, List, Optional, Tuple

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.live import Live

from ..config import (
    ProgressSettings,
    has_saved_progress,
    load_progress_settings,
    save_progress_settings,
)
from ..core.item_actions import ITEM_RULES_CUSTOM_PATH
from ..progress.data_loader import load_game_data
from ..progress.data_update import DownloadError, update_data_snapshot
from ..progress.progress_config import (
    build_quest_index,
    group_quests_by_trader,
    infer_completed_by_trader,
    resolve_active_quests,
)
from ..progress.rules_generator import generate_rules_from_active, write_rules
from ..items.rules_viewer import run_rules_viewer
from .key_reader import key_reader
from .ui_utils import window_for_cursor


@dataclass(frozen=True)
class QuestEntry:
    id: str
    name: str
    trader: str
    sort_order: int


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_quest_value(value: str) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("’", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _build_quest_entries(quests: List[dict]) -> List[QuestEntry]:
    entries: List[QuestEntry] = []
    for quest in quests:
        quest_id = quest.get("id")
        quest_name = quest.get("name")
        trader = quest.get("trader") or "Unknown"
        sort_order = int(quest.get("sortOrder") or 0)
        if not quest_id or not quest_name:
            continue
        entries.append(
            QuestEntry(
                id=str(quest_id),
                name=str(quest_name),
                trader=str(trader),
                sort_order=sort_order,
            )
        )
    entries.sort(key=lambda entry: (entry.trader, entry.sort_order, entry.name))
    return entries


def _quest_matches(query: str, quests: Iterable[QuestEntry]) -> List[QuestEntry]:
    normalized = _normalize_quest_value(query)
    if not normalized:
        return []

    exact: List[QuestEntry] = []
    partial: List[Tuple[Tuple[int, int], QuestEntry]] = []
    for quest in quests:
        if query == quest.id:
            exact.append(quest)
            continue
        name_norm = _normalize_quest_value(quest.name)
        if normalized == name_norm:
            exact.append(quest)
            continue
        if normalized in name_norm:
            score = (name_norm.find(normalized), len(name_norm))
            partial.append((score, quest))

    if exact:
        return exact

    partial.sort(key=lambda item: item[0])
    return [quest for _, quest in partial]


def _pick_from_matches(
    console: Console, matches: List[QuestEntry], prompt_label: str
) -> Optional[QuestEntry]:
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    table = Table(title="Matching quests", show_lines=False)
    table.add_column("No.", style="cyan", justify="right")
    table.add_column("Quest")
    table.add_column("Trader", style="dim")
    for idx, quest in enumerate(matches, start=1):
        table.add_row(str(idx), quest.name, quest.trader)
    console.print(table)

    while True:
        choice = Prompt.ask(prompt_label, default="1")
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(matches):
                return matches[number - 1]
        console.print("[yellow]Please enter a valid number.[/yellow]")


def _resolve_quest_input(
    console: Console,
    query: str,
    trader: str,
    trader_quests: List[QuestEntry],
    all_quests: List[QuestEntry],
) -> Optional[QuestEntry]:
    matches = _quest_matches(query, trader_quests)
    if matches:
        return _pick_from_matches(console, matches, "Choose quest number")

    other_matches = _quest_matches(query, all_quests)
    if other_matches:
        console.print(
            f"[yellow]No matches for {trader}, but found quests under other traders.[/yellow]"
        )
        return _pick_from_matches(console, other_matches, "Choose quest number")

    console.print("[yellow]No matching quests found.[/yellow]")
    return None


def _render_snapshot_status(console: Console) -> None:
    try:
        game_data = load_game_data()
    except FileNotFoundError:
        console.print("[yellow]Data snapshot: missing[/yellow]")
        return
    last_updated = game_data.metadata.get("lastUpdated", "unknown")
    source = game_data.metadata.get("source", "unknown")
    version = game_data.metadata.get("version", "unknown")
    console.print(f"[dim]Data snapshot: {last_updated} • {source} • {version}[/dim]")


def _render_progress_status(console: Console, settings: ProgressSettings) -> None:
    if not has_saved_progress(settings):
        console.print("[dim]Progress: not set[/dim]")
        return

    active_count = len(settings.active_quests)
    completed_count = len(settings.completed_quests)
    hideout_count = len(settings.hideout_levels)
    last_updated = settings.last_updated or "unknown"
    all_quests = "Yes" if settings.all_quests_completed else "No"

    console.print(
        "[dim]Progress: saved | "
        f"Active quests: {active_count} | "
        f"Completed quests: {completed_count} | "
        f"Workshops set: {hideout_count} | "
        f"All quests completed: {all_quests} | "
        f"Updated: {last_updated}[/dim]"
    )


def _collect_active_quests_by_trader(
    console: Console,
    quest_entries: List[QuestEntry],
    existing_active_ids: Optional[List[str]] = None,
) -> List[str]:
    active_ids: List[str] = []
    existing_active_ids = existing_active_ids or []
    existing_active = {quest_id: True for quest_id in existing_active_ids}

    by_trader: Dict[str, List[QuestEntry]] = {}
    for quest in quest_entries:
        by_trader.setdefault(quest.trader, []).append(quest)

    for trader, quests in sorted(by_trader.items()):
        console.print(f"\n[bold]{trader}[/bold]")
        saved_entries = [q for q in quests if q.id in existing_active]
        saved_names = [q.name for q in saved_entries]
        used_saved = False
        if saved_names:
            console.print(f"[dim]Saved active quests: {', '.join(saved_names)}[/dim]")
            if Confirm.ask("Use saved quests for this trader?", default=True):
                for quest in saved_entries:
                    if quest.id not in active_ids:
                        active_ids.append(quest.id)
                used_saved = True

        if used_saved and not Confirm.ask(
            "Add more quests for this trader?", default=False
        ):
            continue

        console.print("[dim]Enter active quests for this trader (Enter to skip).[/dim]")
        while True:
            raw = Prompt.ask("Quest name or id", default="", show_default=False)
            raw = raw.strip()
            if not raw:
                break

            resolved = _resolve_quest_input(console, raw, trader, quests, quest_entries)
            if not resolved:
                continue
            if resolved.id in active_ids:
                console.print("[yellow]Already added.[/yellow]")
                continue
            active_ids.append(resolved.id)
            console.print(f"[green]Added:[/green] {resolved.name}")

    return active_ids


def review_quests(
    console: Console,
    quest_entries: List[QuestEntry],
    completed_ids: List[str],
    active_ids: List[str],
) -> Tuple[List[str], List[str], bool]:
    completed = set(completed_ids)
    active = set(active_ids)
    original_completed = set(completed)
    original_active = set(active)

    cursor = 0

    def _status_label(entry: QuestEntry) -> Text:
        if entry.id in completed:
            return Text("✓", style="green")
        if entry.id in active:
            return Text("A", style="cyan")
        return Text("·", style="dim")

    def _render() -> Panel:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Status", width=6)
        table.add_column("Quest", ratio=3)
        table.add_column("Trader", ratio=1, style="dim")

        max_rows = max(6, console.size.height - 10)
        start, end = window_for_cursor(len(quest_entries), cursor, max_rows)

        for idx in range(start, end):
            entry = quest_entries[idx]
            style = "reverse" if idx == cursor else None
            table.add_row(_status_label(entry), entry.name, entry.trader, style=style)

        help_text = Text(
            "↑/↓ move • PgUp/PgDn jump • Space toggle completed • Enter save • q cancel",
            style="dim",
        )
        header = Text("Review Quest Completion", style="bold")
        footer = Text(
            f"Completed: {len(completed)} • Active: {len(active)} • Total: {len(quest_entries)}",
            style="dim",
        )
        return Panel(Group(header, table, help_text, footer), border_style="cyan")

    with key_reader() as read_key:
        with Live(
            _render(), console=console, refresh_per_second=20, transient=True
        ) as live:
            while True:
                key = read_key()
                if key.name == "UP":
                    cursor = max(0, cursor - 1)
                elif key.name == "DOWN":
                    cursor = min(len(quest_entries) - 1, cursor + 1)
                elif key.name == "PAGE_UP":
                    cursor = max(0, cursor - 10)
                elif key.name == "PAGE_DOWN":
                    cursor = min(len(quest_entries) - 1, cursor + 10)
                elif key.name == "HOME":
                    cursor = 0
                elif key.name == "END":
                    cursor = len(quest_entries) - 1
                elif key.name == "CHAR" and key.char in {" ", "x", "X"}:
                    entry = quest_entries[cursor]
                    if entry.id in completed:
                        completed.remove(entry.id)
                    else:
                        completed.add(entry.id)
                        active.discard(entry.id)
                elif key.name == "ENTER":
                    return sorted(completed), sorted(active), False
                elif key.name == "ESC" or (
                    key.name == "CHAR" and key.char in {"q", "Q"}
                ):
                    return (
                        sorted(original_completed),
                        sorted(original_active),
                        True,
                    )
                live.update(_render(), refresh=True)


@dataclass
class HideoutModule:
    id: str
    name: str
    max_level: int


def _build_hideout_modules(hideout_modules: List[dict]) -> List[HideoutModule]:
    modules: List[HideoutModule] = []
    for module in hideout_modules:
        module_id = module.get("id")
        max_level = int(module.get("maxLevel", 0) or 0)
        if not module_id or max_level <= 0:
            continue
        if module_id in {"stash", "workbench"}:
            continue
        name = module.get("name", module_id)
        modules.append(
            HideoutModule(id=str(module_id), name=str(name), max_level=max_level)
        )
    return modules


def edit_hideout_levels(
    console: Console,
    hideout_modules: List[dict],
    existing_levels: Optional[Dict[str, int]] = None,
) -> Optional[Dict[str, int]]:
    entries = _build_hideout_modules(hideout_modules)
    if not entries:
        console.print("[yellow]No workshop modules found.[/yellow]")
        return {}

    levels: Dict[str, int] = {}
    existing_levels = existing_levels or {}
    for entry in entries:
        current = existing_levels.get(entry.id, 0)
        if current < 0:
            current = 0
        if current > entry.max_level:
            current = entry.max_level
        levels[entry.id] = current

    cursor = 0

    def _render_levels() -> Panel:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("", width=2)
        table.add_column("Workshop", ratio=2)
        table.add_column("Level", ratio=4)

        for idx, entry in enumerate(entries):
            selected = idx == cursor
            pointer = Text("➤" if selected else " ", style="cyan")
            level_text = Text()
            for level in range(entry.max_level + 1):
                label = f"{level}"
                if level == levels.get(entry.id, 0):
                    tag = f"[{label}]"
                    style = "bold white on blue" if selected else "bold green"
                    level_text.append(f"{tag} ", style=style)
                else:
                    level_text.append(f"{label} ", style="dim")
            row_style = "reverse" if selected else None
            table.add_row(pointer, entry.name, level_text, style=row_style)

        help_text = Text(
            "↑/↓ select • ←/→ change • 0-9 set • m=max • Enter save • q cancel",
            style="dim",
        )
        header = Text("Set Workshop Levels", style="bold")
        return Panel(Group(header, table, help_text), border_style="cyan")

    with key_reader() as read_key:
        with Live(
            _render_levels(), console=console, refresh_per_second=20, transient=True
        ) as live:
            while True:
                key = read_key()
                if key.name == "UP":
                    cursor = max(0, cursor - 1)
                elif key.name == "DOWN":
                    cursor = min(len(entries) - 1, cursor + 1)
                elif key.name == "LEFT":
                    entry = entries[cursor]
                    levels[entry.id] = max(0, levels[entry.id] - 1)
                elif key.name == "RIGHT":
                    entry = entries[cursor]
                    levels[entry.id] = min(entry.max_level, levels[entry.id] + 1)
                elif key.name == "HOME":
                    entry = entries[cursor]
                    levels[entry.id] = 0
                elif key.name == "END":
                    entry = entries[cursor]
                    levels[entry.id] = entry.max_level
                elif key.name == "CHAR":
                    if key.char and key.char.isdigit():
                        entry = entries[cursor]
                        value = int(key.char)
                        if 0 <= value <= entry.max_level:
                            levels[entry.id] = value
                    elif key.char in {"m", "M"}:
                        entry = entries[cursor]
                        levels[entry.id] = entry.max_level
                    elif key.char in {"q", "Q"}:
                        return None
                elif key.name == "ESC":
                    return None
                elif key.name == "ENTER":
                    return levels
                live.update(_render_levels(), refresh=True)


def _compute_completed_quests(
    quest_entries: List[QuestEntry],
    active_ids: List[str],
) -> List[str]:
    quests_by_trader: Dict[str, List[dict]] = {}
    for entry in quest_entries:
        quests_by_trader.setdefault(entry.trader, []).append(
            {
                "id": entry.id,
                "name": entry.name,
                "sortOrder": entry.sort_order,
            }
        )
    for trader, quests in quests_by_trader.items():
        quests.sort(key=lambda quest: quest.get("sortOrder") or 0)
        quests_by_trader[trader] = quests

    quest_index = build_quest_index(quests_by_trader)
    active_resolved, missing = resolve_active_quests(active_ids, quest_index)
    if missing:
        raise ValueError(f"Active quests not found: {', '.join(missing)}")
    return infer_completed_by_trader(quests_by_trader, active_resolved)


def _display_rules_summary(console: Console, output: Dict[str, object]) -> None:
    counts = Counter(item.get("action") for item in output.get("items", []))
    summary = ", ".join(
        f"{key}={counts.get(key, 0)}" for key in ("keep", "sell", "recycle")
    )
    console.print(f"\n[green]Rules written to {ITEM_RULES_CUSTOM_PATH}[/green]")
    console.print(f"Items: {output.get('metadata', {}).get('itemCount', 0)}")
    if summary:
        console.print(f"Summary: {summary}")


def generate_rules_from_saved_progress(console: Console) -> int:
    settings = load_progress_settings()
    if not has_saved_progress(settings):
        console.print("[yellow]No saved progress found. Run setup first.[/yellow]")
        return 1

    try:
        output = generate_rules_from_active(
            settings.active_quests,
            settings.hideout_levels,
            all_quests_completed=settings.all_quests_completed,
            completed_quests_override=settings.completed_quests,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    write_rules(output, ITEM_RULES_CUSTOM_PATH)
    _display_rules_summary(console, output)
    return 0


def review_saved_quests(console: Console) -> int:
    try:
        game_data = load_game_data()
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    settings = load_progress_settings()
    if not has_saved_progress(settings):
        console.print("[yellow]No saved progress found.[/yellow]")
        return 1

    quest_entries = _build_quest_entries(game_data.quests)
    completed, active, _canceled = review_quests(
        console,
        quest_entries,
        settings.completed_quests,
        settings.active_quests,
    )
    updated = ProgressSettings(
        all_quests_completed=(len(completed) == len(quest_entries)),
        active_quests=active,
        completed_quests=completed,
        hideout_levels=settings.hideout_levels,
        last_updated=_iso_now(),
    )
    save_progress_settings(updated)
    console.print("[green]Quest progress saved.[/green]")
    return 0


def edit_saved_workshops(console: Console) -> int:
    try:
        game_data = load_game_data()
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    settings = load_progress_settings()
    if not has_saved_progress(settings):
        console.print("[yellow]No saved progress found.[/yellow]")
        return 1

    levels = edit_hideout_levels(
        console,
        game_data.hideout_modules,
        existing_levels=settings.hideout_levels,
    )
    if levels is None:
        console.print("[yellow]Workshop edit canceled.[/yellow]")
        return 1

    updated = ProgressSettings(
        all_quests_completed=settings.all_quests_completed,
        active_quests=settings.active_quests,
        completed_quests=settings.completed_quests,
        hideout_levels=levels,
        last_updated=_iso_now(),
    )
    save_progress_settings(updated)
    console.print("[green]Workshop levels saved.[/green]")
    return 0


def run_progress_wizard(console: Optional[Console] = None) -> int:
    console = console or Console()
    try:
        game_data = load_game_data()
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    quest_entries = _build_quest_entries(game_data.quests)
    settings = load_progress_settings()

    console.print(Panel("Generate rules from your progress", style="cyan"))

    all_quests_completed = Confirm.ask(
        "Have you completed all quests?",
        default=settings.all_quests_completed,
    )

    active_ids: List[str] = []
    if not all_quests_completed:
        active_ids = _collect_active_quests_by_trader(
            console,
            quest_entries,
            existing_active_ids=settings.active_quests,
        )
        if not active_ids:
            console.print("[yellow]No active quests entered.[/yellow]")
            return 1

    console.print()
    console.print("[bold]Workshop levels[/bold]")
    hideout_levels = edit_hideout_levels(
        console,
        game_data.hideout_modules,
        existing_levels=settings.hideout_levels,
    )
    if hideout_levels is None:
        console.print("[yellow]Workshop input canceled.[/yellow]")
        return 1

    try:
        if all_quests_completed:
            completed_ids = [q.id for q in quest_entries]
        else:
            completed_ids = _compute_completed_quests(quest_entries, active_ids)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    if Confirm.ask("Review quest completion list?", default=False):
        completed_ids, active_ids, canceled = review_quests(
            console,
            quest_entries,
            completed_ids,
            active_ids,
        )
        if canceled:
            console.print(
                "[yellow]Quest review canceled; keeping previous selections.[/yellow]"
            )
        all_quests_completed = len(completed_ids) == len(quest_entries)

    progress_settings = ProgressSettings(
        all_quests_completed=all_quests_completed,
        active_quests=sorted(set(active_ids)),
        completed_quests=sorted(set(completed_ids)),
        hideout_levels=hideout_levels,
        last_updated=_iso_now(),
    )
    save_progress_settings(progress_settings)

    try:
        output = generate_rules_from_active(
            progress_settings.active_quests,
            progress_settings.hideout_levels,
            all_quests_completed=progress_settings.all_quests_completed,
            completed_quests_override=progress_settings.completed_quests,
        )
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    write_rules(output, ITEM_RULES_CUSTOM_PATH)
    _display_rules_summary(console, output)

    if Confirm.ask("Review quests/workshops/rules now?", default=False):
        while True:
            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1[/cyan]", "Review quests")
            table.add_row("[cyan]2[/cyan]", "Edit workshop levels")
            table.add_row("[cyan]3[/cyan]", "Review / edit rules")
            table.add_row("[cyan]b[/cyan]", "Back")
            console.print(table)
            choice = Prompt.ask("Choose an option", default="b")
            if choice == "1":
                review_saved_quests(console)
                continue
            if choice == "2":
                edit_saved_workshops(console)
                continue
            if choice == "3":
                run_rules_viewer(console)
                continue
            if choice in {"b", "back", "q", "quit"}:
                break

    return 0


def run_update_data(console: Console) -> int:
    console.print("\nRefreshing embedded game data...")
    try:
        metadata = update_data_snapshot()
    except DownloadError as exc:
        console.print(f"[red]Download failed:[/red] {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Update failed:[/red] {exc}")
        return 1

    console.print("[green]Update complete.[/green]")
    console.print(f"Items: {metadata.get('itemCount', 0)}")
    console.print(f"Quests: {metadata.get('questCount', 0)}")
    console.print(f"Last updated: {metadata.get('lastUpdated', 'unknown')}")
    return 0


def show_progress_menu(console: Optional[Console] = None) -> int:
    console = console or Console()
    while True:
        console.print("\n[bold cyan]Game Progress[/bold cyan]")
        _render_snapshot_status(console)
        _render_progress_status(console, load_progress_settings())

        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1[/cyan]", "Set up / update progress")
        table.add_row("[cyan]2[/cyan]", "Review quests")
        table.add_row("[cyan]3[/cyan]", "Edit workshop levels")
        table.add_row("[cyan]4[/cyan]", "Generate rules from saved progress")
        table.add_row("[cyan]5[/cyan]", "Update game data snapshot")
        table.add_row("[cyan]6[/cyan]", "Reset saved progress")
        table.add_row("[cyan]b[/cyan]", "Back")
        console.print(table)

        choice = Prompt.ask("Choose an option", default="b")
        if choice == "1":
            run_progress_wizard(console)
            continue
        if choice == "2":
            review_saved_quests(console)
            continue
        if choice == "3":
            edit_saved_workshops(console)
            continue
        if choice == "4":
            generate_rules_from_saved_progress(console)
            continue
        if choice == "5":
            run_update_data(console)
            continue
        if choice == "6":
            if Confirm.ask(
                "Reset saved progress? This clears quests + workshop levels.",
                default=False,
            ):
                save_progress_settings(ProgressSettings())
                console.print("[green]Progress reset.[/green]")
            continue
        if choice in {"b", "back", "q", "quit"}:
            return 0

        console.print("[yellow]Invalid choice.[/yellow]")
