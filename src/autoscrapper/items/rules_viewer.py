from __future__ import annotations

from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.group import Group

from .rules_cli import (
    CUSTOM_RULES_PATH,
    active_rules_path,
    load_rules,
    normalize_action,
    save_custom_rules,
    using_custom_rules,
)
from ..cli.key_reader import key_reader
from ..cli.ui_utils import window_for_cursor


def _display_action(item: dict) -> str:
    action = item.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip().upper()
    decisions = item.get("decision")
    if isinstance(decisions, list):
        return ", ".join(str(d).upper() for d in decisions if isinstance(d, str))
    return ""


def _filter_indices(items: List[dict], query: str) -> List[int]:
    if not query:
        return list(range(len(items)))
    q = query.lower().strip()
    matches: List[int] = []
    for idx, item in enumerate(items):
        name = str(item.get("name", "")).lower()
        item_id = str(item.get("id", "")).lower()
        if q in name or (item_id and q in item_id):
            matches.append(idx)
    return matches


def _prompt_action(console: Console, default: Optional[str] = None) -> str:
    while True:
        raw = Prompt.ask("Action (keep/sell/recycle)", default=default or "keep")
        action = normalize_action(raw)
        if action:
            return action
        console.print("[yellow]Please enter keep, sell, or recycle.[/yellow]")


def _prompt_non_empty(console: Console, label: str, default: str = "") -> str:
    while True:
        value = Prompt.ask(label, default=default).strip()
        if value:
            return value
        console.print("[yellow]Value cannot be empty.[/yellow]")


def _render_view(
    console: Console,
    items: List[dict],
    filtered: List[int],
    cursor: int,
    query: str,
    search_buffer: str,
    search_mode: bool,
) -> Panel:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("No.", width=4, justify="right", style="cyan")
    table.add_column("Name", ratio=3)
    table.add_column("Action", width=10, style="magenta")

    max_rows = max(6, console.size.height - 14)
    start, end = window_for_cursor(len(filtered), cursor, max_rows)

    for row_idx in range(start, end):
        item_idx = filtered[row_idx]
        item = items[item_idx]
        style = "reverse" if row_idx == cursor else None
        table.add_row(
            str(row_idx + 1),
            str(item.get("name", "")),
            _display_action(item),
            style=style,
        )

    details = Table(show_header=False, box=None)
    if filtered:
        current = items[filtered[cursor]]
        details.add_row("Name", str(current.get("name", "")))
        details.add_row("ID", str(current.get("id", "")))
        details.add_row("Action", _display_action(current))
        analysis = current.get("analysis")
        if isinstance(analysis, list) and analysis:
            preview = analysis[:4]
            for idx, reason in enumerate(preview, start=1):
                details.add_row("Reason" if idx == 1 else "", str(reason))
            if len(analysis) > len(preview):
                details.add_row("", f"… +{len(analysis) - len(preview)} more")
    else:
        details.add_row("", "No rules match the current filter.")

    status = "Custom" if using_custom_rules() else "Default"
    header = Text(f"Rules Viewer • {status} ({active_rules_path()})", style="bold")

    if search_mode:
        search_line = Text(f"Search: {search_buffer}", style="cyan")
    else:
        search_line = Text(
            f"Filter: {query or 'None'} • Total {len(items)} • Showing {len(filtered)}",
            style="dim",
        )

    help_text = Text(
        "↑/↓ move • PgUp/PgDn jump • / search • c clear • k/s/r set • e edit • a add • d delete • z reset • q quit",
        style="dim",
    )

    return Panel(Group(header, table, details, search_line, help_text), border_style="cyan")


def run_rules_viewer(console: Optional[Console] = None) -> int:
    console = console or Console()

    cursor = 0
    query = ""
    search_buffer = ""
    search_mode = False

    while True:
        payload = load_rules()
        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []
        filtered = _filter_indices(items, query)
        cursor = max(0, min(cursor, max(0, len(filtered) - 1)))

        action: Optional[str] = None

        with key_reader() as read_key:
            with Live(
                _render_view(
                    console,
                    items,
                    filtered,
                    cursor,
                    query,
                    search_buffer,
                    search_mode,
                ),
                console=console,
                refresh_per_second=20,
                transient=True,
            ) as live:
                while True:
                    key = read_key()
                    if search_mode:
                        if key.name == "ENTER":
                            query = search_buffer.strip()
                            search_mode = False
                            filtered = _filter_indices(items, query)
                            cursor = 0
                        elif key.name == "ESC":
                            search_mode = False
                            search_buffer = ""
                        elif key.name == "BACKSPACE":
                            search_buffer = search_buffer[:-1]
                        elif key.name == "CHAR" and key.char:
                            if key.char.isprintable():
                                search_buffer += key.char
                        live.update(
                            _render_view(
                                console,
                                items,
                                filtered,
                                cursor,
                                query,
                                search_buffer,
                                search_mode,
                            ),
                            refresh=True,
                        )
                        continue

                    if key.name == "UP":
                        cursor = max(0, cursor - 1)
                    elif key.name == "DOWN":
                        cursor = min(len(filtered) - 1, cursor + 1)
                    elif key.name == "PAGE_UP":
                        cursor = max(0, cursor - 10)
                    elif key.name == "PAGE_DOWN":
                        cursor = min(len(filtered) - 1, cursor + 10)
                    elif key.name == "HOME":
                        cursor = 0
                    elif key.name == "END":
                        cursor = max(0, len(filtered) - 1)
                    elif key.name == "CHAR":
                        if key.char in {"/"}:
                            search_mode = True
                            search_buffer = ""
                        elif key.char in {"c", "C"}:
                            query = ""
                            cursor = 0
                            filtered = _filter_indices(items, query)
                        elif key.char in {"k", "K", "s", "S", "r", "R"}:
                            if not filtered:
                                continue
                            idx = filtered[cursor]
                            action_value = normalize_action(key.char)
                            if action_value:
                                items[idx]["action"] = action_value
                                payload["items"] = items
                                save_custom_rules(payload)
                        elif key.char in {"e", "E"}:
                            action = "edit"
                            break
                        elif key.char in {"a", "A"}:
                            action = "add"
                            break
                        elif key.char in {"d", "D"}:
                            action = "delete"
                            break
                        elif key.char in {"q", "Q"}:
                            action = "quit"
                            break
                        elif key.char in {"z", "Z"}:
                            action = "reset"
                            break
                    elif key.name == "ESC":
                        action = "quit"
                        break

                    live.update(
                        _render_view(
                            console,
                            items,
                            filtered,
                            cursor,
                            query,
                            search_buffer,
                            search_mode,
                        ),
                        refresh=True,
                    )

        if action is None:
            continue
        if action == "quit":
            console.print("[green]Goodbye![/green]")
            return 0
        if action == "reset":
            if Confirm.ask(
                "Reset to default rules? This will delete your custom rules.",
                default=False,
            ):
                CUSTOM_RULES_PATH.unlink(missing_ok=True)
                console.print("[green]Custom rules removed. Defaults restored.[/green]")
            continue
        if action == "delete":
            if not filtered:
                console.print("[yellow]No rule selected.[/yellow]")
                continue
            item = items[filtered[cursor]]
            name = str(item.get("name", ""))
            if Confirm.ask(f"Delete '{name}'?", default=False):
                items.pop(filtered[cursor])
                payload["items"] = items
                save_custom_rules(payload)
                console.print(f"[green]Removed '{name}'.[/green]")
            continue
        if action == "add":
            name = _prompt_non_empty(console, "Item name")
            action_value = _prompt_action(console)
            item_id = Prompt.ask("Item id (optional)", default="").strip()
            entry = {"name": name, "action": action_value}
            if item_id:
                entry["id"] = item_id
            items.append(entry)
            payload["items"] = items
            save_custom_rules(payload)
            console.print(f"[green]Added '{name}'.[/green]")
            continue
        if action == "edit":
            if not filtered:
                console.print("[yellow]No rule selected.[/yellow]")
                continue
            item = items[filtered[cursor]]
            name = _prompt_non_empty(console, "Item name", str(item.get("name", "")))
            action_value = _prompt_action(console, default=str(item.get("action", "keep")))
            item_id = Prompt.ask("Item id (optional)", default=str(item.get("id", "") or "")).strip()
            item["name"] = name
            item["action"] = action_value
            if item_id:
                item["id"] = item_id
            elif "id" in item:
                item.pop("id", None)
            payload["items"] = items
            save_custom_rules(payload)
            console.print("[green]Updated rule.[/green]")
            continue
