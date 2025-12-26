from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, cast

from ..interaction.inventory_grid import Cell

Decision = Literal["KEEP", "RECYCLE", "SELL", "CRAFTING MATERIAL"]
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


VALID_DECISIONS = {"KEEP", "RECYCLE", "SELL", "CRAFTING MATERIAL"}
ITEM_ACTIONS_PATH = (
    Path(__file__).resolve().parent.parent / "items" / "items_actions.json"
)


def normalize_item_name(name: str) -> str:
    return name.strip().lower()


def clean_ocr_text(raw: str) -> str:
    text = " ".join(raw.split())
    text = re.sub(r"[^-A-Za-z0-9 '()\\]+", "", text)
    return text.strip()


def load_item_actions(path: Path = ITEM_ACTIONS_PATH) -> ActionMap:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"[warn] Item actions file not found at {path}; defaulting to skip actions."
        )
        return {}
    except json.JSONDecodeError as exc:
        print(
            f"[warn] Could not parse item actions file {path}: {exc}; defaulting to skip actions."
        )
        return {}

    if not isinstance(raw, list):
        print(
            f"[warn] Item actions file {path} must be a JSON array; defaulting to skip actions."
        )
        return {}

    actions: ActionMap = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        decisions = entry.get("decision")
        if not isinstance(name, str) or not isinstance(decisions, list):
            continue

        normalized_name = normalize_item_name(name)
        cleaned: DecisionList = []
        for decision in decisions:
            if not isinstance(decision, str):
                continue
            candidate = decision.strip().upper()
            if candidate in VALID_DECISIONS:
                cleaned.append(cast(Decision, candidate))
        if normalized_name and cleaned:
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
