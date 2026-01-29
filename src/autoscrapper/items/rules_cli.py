"""
Interactive CLI for managing item rules.
Uses Rich for output styling. Intended to be run with `python -m autoscrapper rules`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

DEFAULT_RULES_PATH = Path(__file__).with_name("items_rules.default.json")
CUSTOM_RULES_PATH = Path(__file__).with_name("items_rules.custom.json")
console = Console()


def active_rules_path() -> Path:
    return CUSTOM_RULES_PATH if CUSTOM_RULES_PATH.exists() else DEFAULT_RULES_PATH


def using_custom_rules() -> bool:
    return CUSTOM_RULES_PATH.exists()


def _coerce_payload(raw: object) -> dict:
    if isinstance(raw, dict):
        items = raw.get("items")
        if not isinstance(items, list):
            items = []
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        return {"metadata": metadata, "items": items}

    if isinstance(raw, list):
        return {"metadata": {}, "items": raw}

    return {"metadata": {}, "items": []}


def load_rules(path: Optional[Path] = None) -> dict:
    rules_path = path or active_rules_path()
    if not rules_path.exists():
        return {"metadata": {}, "items": []}
    with rules_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return _coerce_payload(raw)


def save_rules(payload: dict, path: Path) -> None:
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    metadata = (
        payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    )
    metadata["itemCount"] = len(items)
    payload = {"metadata": metadata, "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def save_custom_rules(payload: dict) -> None:
    save_rules(payload, CUSTOM_RULES_PATH)


def reset_custom_rules(_: Optional[List[dict]] = None) -> None:
    if not CUSTOM_RULES_PATH.exists():
        console.print("[yellow]Already using default rules.[/yellow]")
        return
    if Confirm.ask(
        "Reset to default rules? This will delete your custom rules.",
        default=False,
    ):
        CUSTOM_RULES_PATH.unlink(missing_ok=True)
        console.print("[green]Custom rules removed. Defaults restored.[/green]")


def _display_action(item: dict) -> str:
    action = item.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip().upper()
    decisions = item.get("decision")
    if isinstance(decisions, list):
        return ", ".join(str(d).upper() for d in decisions if isinstance(d, str))
    return ""


def show_table(items: List[dict], title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("No.", style="cyan", justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Action", style="magenta")
    for idx, item in enumerate(items, start=1):
        table.add_row(str(idx), item.get("name", ""), _display_action(item))
    console.print(table)


def normalize_action(value: str) -> Optional[str]:
    raw = value.strip().lower()
    if raw in {"k", "keep"}:
        return "keep"
    if raw in {"s", "sell"}:
        return "sell"
    if raw in {"r", "recycle"}:
        return "recycle"
    return None


def parse_action(default: Optional[str] = None) -> str:
    while True:
        raw = Prompt.ask(
            "Enter action (keep/sell/recycle)",
            default=default,
        )
        action = normalize_action(raw)
        if action:
            return action
        console.print("[yellow]Please enter keep, sell, or recycle.[/yellow]")


def find_matches(items: List[dict], query: str) -> List[dict]:
    q = query.lower().strip()
    matches: List[dict] = []
    for item in items:
        name = str(item.get("name", "")).lower()
        item_id = str(item.get("id", "")).lower()
        if q in name or (item_id and q == item_id):
            matches.append(item)
    return matches


def pick_from_matches(matches: List[dict], title: str) -> Optional[dict]:
    if not matches:
        return None
    show_table(matches, title)
    default_choice = "1"
    while True:
        choice = Prompt.ask("Select number from the table", default=default_choice)
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(matches):
                return matches[number - 1]
        console.print("[yellow]Please enter a valid number from the table.[/yellow]")


def choose_item(items: List[dict], action: str) -> Optional[dict]:
    if not items:
        console.print("[yellow]No items available.[/yellow]")
        return None
    query = Prompt.ask(f"Enter item name or id to {action}")
    matches = find_matches(items, query)
    if not matches:
        console.print("[yellow]No matching items found.[/yellow]")
        return None
    if len(matches) == 1:
        return matches[0]
    return pick_from_matches(matches, f"Multiple matches for '{query}'")


def view_all(payload: dict) -> None:
    items = payload.get("items", [])
    if not items:
        console.print("[yellow]No rules found.[/yellow]")
        return
    show_table(items, "All Item Rules")


def view_single(payload: dict) -> None:
    items = payload.get("items", [])
    chosen = choose_item(items, "view")
    if chosen:
        show_table([chosen], f"Rule for '{chosen.get('name', '')}'")


def add_item(payload: dict) -> None:
    items = payload.get("items", [])
    name = ""
    while not name:
        name = Prompt.ask("Enter new item name").strip()
        if not name:
            console.print("[yellow]Name cannot be empty.[/yellow]")
    existing = [item for item in items if item.get("name", "").lower() == name.lower()]
    if existing:
        console.print("[yellow]An item with this name already exists.[/yellow]")
        choice = Prompt.ask(
            "Edit existing (e), add another entry (a), or cancel (c)?",
            choices=["e", "a", "c"],
            default="e",
        )
        if choice == "c":
            return
        if choice == "e":
            target = pick_from_matches(existing, f"Matches for '{name}'")
            if target:
                edit_item(payload, target)
            return
    action = parse_action()
    item_id = Prompt.ask("Enter item id (optional)", default="").strip()
    entry = {"name": name, "action": action}
    if item_id:
        entry["id"] = item_id
    items.append(entry)
    payload["items"] = items
    save_custom_rules(payload)
    console.print(f"[green]Added '{name}'.[/green]")


def edit_item(payload: dict, existing: Optional[dict] = None) -> None:
    items = payload.get("items", [])
    chosen = existing or choose_item(items, "edit")
    if not chosen:
        return
    new_name = Prompt.ask("Enter new name", default=chosen.get("name", "")).strip()
    new_name = new_name or chosen.get("name", "")
    new_action = parse_action(default=str(chosen.get("action", "keep")))
    chosen["name"] = new_name
    chosen["action"] = new_action
    save_custom_rules(payload)
    console.print("[green]Updated item rule.[/green]")


def remove_item(payload: dict) -> None:
    items = payload.get("items", [])
    chosen = choose_item(items, "remove")
    if not chosen:
        return
    name = chosen.get("name", "")
    if Confirm.ask(f"Delete '{name}'?", default=False):
        payload["items"] = [item for item in items if item is not chosen]
        save_custom_rules(payload)
        console.print(f"[green]Removed '{name}'.[/green]")


def main() -> None:
    console.print("[bold cyan]Item Rules Manager[/bold cyan]")
    actions = {
        "1": ("View all rules", view_all),
        "2": ("View one rule", view_single),
        "3": ("Add item rule", add_item),
        "4": ("Edit item rule", edit_item),
        "5": ("Remove item rule", remove_item),
        "6": ("Reset to default rules", reset_custom_rules),
        "q": ("Quit", None),
    }
    while True:
        payload = load_rules()
        status = "Custom" if using_custom_rules() else "Default"
        console.print(f"[dim]Active rules: {status} ({active_rules_path()})[/dim]")
        table = Table(show_header=False, box=None)
        for key, (label, _) in actions.items():
            table.add_row(f"[cyan]{key}[/cyan]", label)
        console.print(table)
        choice = Prompt.ask(
            "Choose an action", choices=list(actions.keys()), default="q"
        )
        if choice == "q":
            console.print("[green]Goodbye![/green]")
            break
        label, handler = actions[choice]
        console.print(f"[bold]{label}[/bold]")
        handler(payload)
        console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted by user.[/red]")
