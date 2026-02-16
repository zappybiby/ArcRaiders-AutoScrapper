from __future__ import annotations

import re
from typing import Dict, List, Tuple


def _norm_key(key: str) -> str:
    normalized = str(key).strip().lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", normalized)


HIDEOUT_ALIASES = {
    "gunsmith": "weapon_bench",
    "weapon bench": "weapon_bench",
    "weapon_bench": "weapon_bench",
    "gear bench": "equipment_bench",
    "gear_bench": "equipment_bench",
    "equipment bench": "equipment_bench",
    "equipment_bench": "equipment_bench",
    "medical lab": "med_station",
    "medical_lab": "med_station",
    "med station": "med_station",
    "med_station": "med_station",
    "explosives station": "explosives_bench",
    "explosives_station": "explosives_bench",
    "explosives bench": "explosives_bench",
    "explosives_bench": "explosives_bench",
    "utility station": "utility_bench",
    "utility_station": "utility_bench",
    "utility bench": "utility_bench",
    "utility_bench": "utility_bench",
    "scrappy": "scrappy",
    "refiner": "refiner",
    "stash": "stash",
    "workbench": "workbench",
}


def normalize_hideout_levels(
    input_levels: Dict[str, int] | None, hideout_modules: List[dict]
) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not input_levels:
        return out

    name_to_id = {
        _norm_key(mod.get("name", "")): mod.get("id") for mod in hideout_modules
    }

    for raw_key, raw_level in input_levels.items():
        key = _norm_key(raw_key)
        alias_id = HIDEOUT_ALIASES.get(key)
        by_name_id = name_to_id.get(key)
        module_id = alias_id or by_name_id or raw_key

        try:
            level_num = int(raw_level)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid hideout level for '{raw_key}': {raw_level}"
            ) from None
        if level_num < 0:
            raise ValueError(f"Invalid hideout level for '{raw_key}': {raw_level}")

        out[module_id] = level_num

    return out


def _normalize_quest_name(value: str) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("’", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def group_quests_by_trader(quests: List[dict]) -> Dict[str, List[dict]]:
    quests_by_trader: Dict[str, List[dict]] = {}
    for quest in quests:
        trader = quest.get("trader") or "Unknown"
        quests_by_trader.setdefault(trader, []).append(quest)

    for trader, quests_list in quests_by_trader.items():
        quests_list.sort(key=lambda q: q.get("sortOrder") or 0)

    return quests_by_trader


def build_quest_index(
    quests_by_trader: Dict[str, List[dict]],
) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    by_id: Dict[str, dict] = {}
    by_name: Dict[str, dict] = {}

    for trader, quests in quests_by_trader.items():
        for idx, quest in enumerate(quests):
            meta = {**quest, "trader": trader, "index": idx}
            quest_id = quest.get("id")
            quest_name = quest.get("name")
            if quest_id:
                by_id[quest_id] = meta
            if quest_name:
                by_name[_normalize_quest_name(quest_name)] = meta

    return by_id, by_name


def resolve_active_quests(
    active_list: List[str], quest_index: Tuple[Dict[str, dict], Dict[str, dict]]
) -> Tuple[List[dict], List[str]]:
    by_id, by_name = quest_index
    resolved: List[dict] = []
    missing: List[str] = []

    for entry in active_list:
        by_id_match = by_id.get(entry)
        by_name_match = by_name.get(_normalize_quest_name(entry))
        found = by_id_match or by_name_match
        if found:
            resolved.append(
                {
                    "id": found.get("id"),
                    "name": found.get("name"),
                    "trader": found.get("trader"),
                    "index": found.get("index"),
                }
            )
        else:
            missing.append(entry)

    return resolved, missing


def infer_completed_by_trader(
    quests_by_trader: Dict[str, List[dict]], active_resolved: List[dict]
) -> List[str]:
    completed = set()
    for active in active_resolved:
        trader = active.get("trader")
        if not trader:
            continue
        quest_list = quests_by_trader.get(trader, [])
        index = active.get("index")
        if index is None:
            continue
        for quest in quest_list[: int(index)]:
            quest_id = quest.get("id")
            if quest_id:
                completed.add(quest_id)
    return list(completed)


def build_completed_quest_ids(
    quests: List[dict],
    quest_progress_by_trader: Dict[str, int] | None,
    completed_quest_ids: List[str] | None,
) -> List[str]:
    completed = set(completed_quest_ids or [])
    if not quest_progress_by_trader:
        return list(completed)

    quests_by_trader = group_quests_by_trader(quests)
    trader_lookup = {
        _norm_key(trader): trader for trader in sorted(quests_by_trader.keys())
    }

    for raw_trader, raw_count in quest_progress_by_trader.items():
        trader_key = trader_lookup.get(_norm_key(raw_trader))
        if not trader_key:
            available = ", ".join(sorted(quests_by_trader.keys()))
            raise ValueError(
                f"Unknown trader '{raw_trader}' in questProgressByTrader. Available traders: {available}"
            )

        quests_for_trader = quests_by_trader.get(trader_key, [])
        try:
            completed_count = int(raw_count)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid completed quest count for trader '{raw_trader}': {raw_count}"
            ) from None

        if completed_count < 0:
            raise ValueError(
                f"Invalid completed quest count for trader '{raw_trader}': {raw_count}"
            )
        if completed_count > len(quests_for_trader):
            raise ValueError(
                f"questProgressByTrader['{raw_trader}'] is {completed_count}, but trader only has {len(quests_for_trader)} quests"
            )

        for quest in quests_for_trader[:completed_count]:
            quest_id = quest.get("id")
            if quest_id:
                completed.add(quest_id)

    return list(completed)
