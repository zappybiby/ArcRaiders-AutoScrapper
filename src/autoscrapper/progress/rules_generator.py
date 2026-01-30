from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .data_loader import GameData, load_game_data
from .decision_engine import DecisionEngine, DecisionReason
from .progress_config import (
    build_quest_index,
    group_quests_by_trader,
    infer_completed_by_trader,
    normalize_hideout_levels,
    resolve_active_quests,
)


def _to_action(decision: DecisionReason) -> str:
    if decision.decision == "keep":
        return "keep"
    if decision.decision == "situational":
        return "keep"
    if decision.recycle_value_exceeds_item:
        return "recycle"
    return "sell"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_rules_from_active(
    active_quests: List[str],
    hideout_levels: Dict[str, int],
    *,
    completed_projects: Optional[List[str]] = None,
    completed_quests_override: Optional[List[str]] = None,
    all_quests_completed: bool = False,
    data_dir: Optional[Path] = None,
) -> Dict[str, object]:
    game_data = load_game_data(data_dir)
    normalized_levels = normalize_hideout_levels(
        hideout_levels, game_data.hideout_modules
    )

    quests_by_trader = group_quests_by_trader(game_data.quests)
    quest_index = build_quest_index(quests_by_trader)
    active_resolved: List[dict] = []
    if active_quests:
        active_resolved, missing = resolve_active_quests(active_quests, quest_index)
        if missing:
            raise ValueError(f"Active quests not found: {', '.join(missing)}")

    if all_quests_completed:
        completed_quests = [
            quest.get("id") for quest in game_data.quests if quest.get("id")
        ]
    elif completed_quests_override is not None:
        completed_quests = completed_quests_override
    else:
        if not active_resolved:
            raise ValueError("No active quests provided.")
        completed_quests = infer_completed_by_trader(quests_by_trader, active_resolved)

    user_progress = {
        "hideoutLevels": normalized_levels,
        "completedQuests": completed_quests,
        "completedProjects": completed_projects or [],
        "lastUpdated": int(datetime.now(timezone.utc).timestamp() * 1000),
    }

    engine = DecisionEngine(
        game_data.items, game_data.hideout_modules, game_data.quests, game_data.projects
    )
    items_with_decisions = engine.get_items_with_decisions(user_progress)

    out_items = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "value": item.get("value"),
            "action": _to_action(item["decision_data"]),
            "analysis": item["decision_data"].reasons,
        }
        for item in items_with_decisions
    ]
    out_items.sort(key=lambda entry: str(entry.get("id", "")))

    metadata = {
        "generatedAt": _iso_now(),
        "data": game_data.metadata,
        "itemCount": len(out_items),
    }
    if active_resolved:
        metadata["activeQuests"] = [
            {
                "id": quest.get("id"),
                "name": quest.get("name"),
                "trader": quest.get("trader"),
            }
            for quest in active_resolved
        ]
    if all_quests_completed:
        metadata["allQuestsCompleted"] = True

    return {"metadata": metadata, "items": out_items}


def write_rules(output: Dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
