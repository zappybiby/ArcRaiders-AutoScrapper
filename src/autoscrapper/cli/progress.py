from __future__ import annotations

from collections import Counter
from typing import Dict, List

from ..core.item_actions import ITEM_RULES_CUSTOM_PATH
from ..progress.data_loader import load_game_data
from ..progress.data_update import DownloadError, update_data_snapshot
from ..progress.rules_generator import generate_rules_from_active, write_rules


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        raw = input(f"{prompt}{suffix}").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter y or n.")


def _prompt_active_quests() -> List[str]:
    print("\nEnter your active quests (one per line).")
    print("Tip: paste multiple lines; press Enter on an empty line when done.")
    lines: List[str] = []
    while True:
        line = input("> ").strip()
        if not line:
            break
        parts = [part.strip() for part in line.replace("|", ",").split(",")]
        lines.extend(part for part in parts if part)
    return lines


def _prompt_level(label: str, max_level: int) -> int:
    prompt = f"{label} (0-{max_level})"
    while True:
        raw = input(f"{prompt} [0]: ").strip().lower()
        if not raw:
            return 0
        if raw in {"m", "max"}:
            return max_level
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a number, or 'max'.")
            continue
        if 0 <= value <= max_level:
            return value
        print(f"Please enter a value between 0 and {max_level}.")


def _prompt_hideout_levels(hideout_modules: List[dict]) -> Dict[str, int]:
    print("\nSet workshop levels (0 = not unlocked).")
    levels: Dict[str, int] = {}
    for module in hideout_modules:
        module_id = module.get("id")
        max_level = int(module.get("maxLevel", 0) or 0)
        if not module_id or max_level <= 0:
            continue
        if module_id in {"stash", "workbench"}:
            continue
        name = module.get("name", module_id)
        levels[module_id] = _prompt_level(name, max_level)
    return levels


def _render_snapshot_status() -> None:
    try:
        game_data = load_game_data()
    except FileNotFoundError:
        print("Data snapshot: missing")
        return
    last_updated = game_data.metadata.get("lastUpdated", "unknown")
    source = game_data.metadata.get("source", "unknown")
    version = game_data.metadata.get("version", "unknown")
    print(f"Data snapshot: {last_updated} • {source} • {version}")


def _run_generate_rules() -> int:
    try:
        game_data = load_game_data()
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    print("\nGenerate rules from active quests + workshop levels")
    all_quests_completed = _prompt_yes_no("Have you completed all quests?", False)
    active_quests: List[str] = []
    if not all_quests_completed:
        active_quests = _prompt_active_quests()
        if not active_quests:
            print("No active quests entered.")
            return 1

    hideout_levels = _prompt_hideout_levels(game_data.hideout_modules)

    try:
        output = generate_rules_from_active(
            active_quests,
            hideout_levels,
            all_quests_completed=all_quests_completed,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    write_rules(output, ITEM_RULES_CUSTOM_PATH)

    counts = Counter(item.get("action") for item in output.get("items", []))
    summary = ", ".join(
        f"{key}={counts.get(key, 0)}" for key in ("keep", "sell", "recycle")
    )
    print(f"\nRules written to {ITEM_RULES_CUSTOM_PATH}")
    print(f"Items: {output.get('metadata', {}).get('itemCount', 0)}")
    if summary:
        print(f"Summary: {summary}")
    return 0


def _run_update_data() -> int:
    print("\nRefreshing embedded game data...")
    try:
        metadata = update_data_snapshot()
    except DownloadError as exc:
        print(f"Download failed: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - surface unexpected failures
        print(f"Update failed: {exc}")
        return 1

    print("Update complete.")
    print(f"Items: {metadata.get('itemCount', 0)}")
    print(f"Quests: {metadata.get('questCount', 0)}")
    print(f"Last updated: {metadata.get('lastUpdated', 'unknown')}")
    return 0


def main(argv=None) -> int:
    print("Game Progress")
    while True:
        _render_snapshot_status()
        print("\n1) Generate rules from progress")
        print("2) Update game data snapshot")
        print("q) Back")

        choice = input("Select an option: ").strip().lower()
        if choice == "1":
            return _run_generate_rules()
        if choice == "2":
            _run_update_data()
            continue
        if choice in {"q", "back", "quit"}:
            return 0
        print("Invalid choice. Please try again.")
