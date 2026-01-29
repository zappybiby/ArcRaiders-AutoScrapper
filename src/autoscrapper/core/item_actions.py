from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, cast

from ..interaction.inventory_grid import Cell

Decision = Literal["KEEP", "RECYCLE", "SELL"]
DecisionList = List[Decision]
ActionMap = Dict[str, DecisionList]


@dataclass
class ItemActionResult:
    page: int
    cell: Cell
    item_name: str
    decision: Optional[Decision]
    action_taken: str
    raw_item_text: Optional[str] = None
    note: Optional[str] = None


VALID_DECISIONS = {"KEEP", "RECYCLE", "SELL"}
ACTION_ALIASES = {
    "keep": "KEEP",
    "sell": "SELL",
    "recycle": "RECYCLE",
    "your_call": "KEEP",
    "your call": "KEEP",
    "sell_or_recycle": "SELL",
    "sell or recycle": "SELL",
    "crafting material": "KEEP",
}
ITEM_RULES_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent / "items" / "items_rules.default.json"
)
ITEM_RULES_CUSTOM_PATH = (
    Path(__file__).resolve().parent.parent / "items" / "items_rules.custom.json"
)
ITEM_RULES_PATH = ITEM_RULES_DEFAULT_PATH


def resolve_item_actions_path(path: Optional[Path] = None) -> Path:
    if path is None or path == ITEM_RULES_DEFAULT_PATH or path == ITEM_RULES_PATH:
        return (
            ITEM_RULES_CUSTOM_PATH
            if ITEM_RULES_CUSTOM_PATH.exists()
            else ITEM_RULES_DEFAULT_PATH
        )
    return path


def normalize_item_name(name: str) -> str:
    return name.strip().lower()


def clean_ocr_text(raw: str) -> str:
    text = " ".join(raw.split())
    text = re.sub(r"[^-A-Za-z0-9 '()\\]+", "", text)
    return text.strip()


def _normalize_action(value: object) -> Optional[Decision]:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    mapped = ACTION_ALIASES.get(key)
    if mapped in VALID_DECISIONS:
        return cast(Decision, mapped)
    candidate = key.upper()
    if candidate in VALID_DECISIONS:
        return cast(Decision, candidate)
    return None


def load_item_actions(path: Optional[Path] = None) -> ActionMap:
    path = resolve_item_actions_path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"[warn] Item rules file not found at {path}; defaulting to skip actions."
        )
        return {}
    except json.JSONDecodeError as exc:
        print(
            f"[warn] Could not parse item rules file {path}: {exc}; defaulting to skip actions."
        )
        return {}

    if isinstance(raw, dict):
        raw_items = raw.get("items", [])
    else:
        raw_items = raw

    if not isinstance(raw_items, list):
        print(
            f"[warn] Item rules file {path} must contain an items list; defaulting to skip actions."
        )
        return {}

    actions: ActionMap = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        normalized_name = normalize_item_name(name)
        if not isinstance(name, str) or not normalized_name:
            continue

        action_value = entry.get("action")
        action = _normalize_action(action_value)
        if action:
            actions[normalized_name] = [action]
            continue

        decisions = entry.get("decision")
        if not isinstance(decisions, list):
            continue

        cleaned: DecisionList = []
        for decision in decisions:
            action = _normalize_action(decision)
            if action:
                cleaned.append(action)

        if cleaned:
            actions[normalized_name] = cleaned

    return actions


def choose_decision(
    item_name: str, actions: ActionMap
) -> Tuple[Optional[Decision], Optional[str]]:
    normalized = normalize_item_name(item_name)
    if not normalized:
        return None, None

    decision_list = actions.get(normalized)
    if not decision_list:
        return None, None

    decision = decision_list[0]
    note = None
    if len(decision_list) > 1:
        note = f"Multiple decisions {decision_list}; chose {decision}."

    return decision, note
