"""
Interactive CLI for managing item rules.
Uses Rich for output styling. Intended to be run with `python -m autoscrapper rules`.
"""

import json
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

DEFAULT_RULES_PATH = Path(__file__).with_name("items_actions.default.json")
CUSTOM_RULES_PATH = Path(__file__).with_name("items_actions.custom.json")
console = Console()


def active_rules_path() -> Path:
    return CUSTOM_RULES_PATH if CUSTOM_RULES_PATH.exists() else DEFAULT_RULES_PATH


def using_custom_rules() -> bool:
    return CUSTOM_RULES_PATH.exists()


def load_items(path: Optional[Path] = None) -> List[dict]:
    rules_path = path or active_rules_path()
    if not rules_path.exists():
        return []
    with rules_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def save_items(items: List[dict], path: Path) -> None:
    ordered = sorted(items, key=lambda entry: entry.get("index", 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(ordered, fp, indent=2)


def save_custom_items(items: List[dict]) -> None:
    save_items(items, CUSTOM_RULES_PATH)


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


def show_table(items: List[dict], title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("Index", style="cyan", justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Decisions", style="magenta")
    for item in items:
        decisions = ", ".join(item.get("decision", []))
        table.add_row(str(item.get("index", "")), item.get("name", ""), decisions)
    console.print(table)


def parse_decisions(default: Optional[List[str]] = None) -> List[str]:
    default_text = ", ".join(default or [])
    while True:
        raw = Prompt.ask(
            "Enter decisions (comma-separated)",
            default=default_text if default else None,
        )
        entries = [
            part.strip() for part in raw.replace(";", ",").split(",") if part.strip()
        ]
        if entries:
            return entries
        console.print("[yellow]Please provide at least one decision.[/yellow]")


def find_matches(items: List[dict], query: str) -> List[dict]:
    if query.isdigit():
        index = int(query)
        return [item for item in items if item.get("index") == index]
    lowered = query.lower()
    return [item for item in items if lowered in item.get("name", "").lower()]


def pick_from_matches(matches: List[dict], title: str) -> Optional[dict]:
    if not matches:
        return None
    show_table(matches, title)
    default_choice = str(matches[0].get("index", ""))
    while True:
        choice = Prompt.ask("Select index from the table", default=default_choice)
        selected = next(
            (item for item in matches if str(item.get("index")) == choice.strip()),
            None,
        )
        if selected:
            return selected
        console.print("[yellow]Please enter a valid index from the table.[/yellow]")


def choose_item(items: List[dict], action: str) -> Optional[dict]:
    if not items:
        console.print("[yellow]No items available.[/yellow]")
        return None
    query = Prompt.ask(f"Enter item name or index to {action}")
    matches = find_matches(items, query.strip())
    if not matches:
        console.print("[yellow]No matching items found.[/yellow]")
        return None
    if len(matches) == 1:
        return matches[0]
    show_table(matches, f"Multiple matches for '{query}'")
    while True:
        choice = Prompt.ask("Select index from the matches")
        picked = [item for item in matches if str(item.get("index")) == choice.strip()]
        if picked:
            return picked[0]
        console.print("[yellow]Please enter a valid index from the table.[/yellow]")


def view_all(items: List[dict]) -> None:
    if not items:
        console.print("[yellow]No rules found.[/yellow]")
        return
    show_table(items, "All Item Rules")


def view_single(items: List[dict]) -> None:
    chosen = choose_item(items, "view")
    if chosen:
        show_table([chosen], f"Rule for '{chosen.get('name', '')}'")


def add_item(items: List[dict]) -> None:
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
                edit_item(items, target)
            return
    decisions = parse_decisions()
    next_index = max((item.get("index", 0) for item in items), default=0) + 1
    items.append({"index": next_index, "name": name, "decision": decisions})
    save_custom_items(items)
    console.print(f"[green]Added '{name}' with index {next_index}.[/green]")


def edit_item(items: List[dict], existing: Optional[dict] = None) -> None:
    chosen = existing or choose_item(items, "edit")
    if not chosen:
        return
    new_name = Prompt.ask("Enter new name", default=chosen.get("name", "")).strip()
    new_name = new_name or chosen.get("name", "")
    new_decisions = parse_decisions(chosen.get("decision", []))
    chosen.update({"name": new_name, "decision": new_decisions})
    save_custom_items(items)
    console.print(f"[green]Updated item {chosen.get('index')}.[/green]")


def remove_item(items: List[dict]) -> None:
    chosen = choose_item(items, "remove")
    if not chosen:
        return
    name = chosen.get("name", "")
    index = chosen.get("index", "")
    if Confirm.ask(f"Delete '{name}' (index {index})?", default=False):
        items[:] = [item for item in items if item.get("index") != index]
        save_custom_items(items)
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
        items = load_items()
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
        handler(items)
        console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted by user.[/red]")
