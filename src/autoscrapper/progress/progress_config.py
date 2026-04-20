from __future__ import annotations

import re


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


def normalize_hideout_levels(input_levels: dict[str, int] | None, hideout_modules: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    if not input_levels:
        return out

    name_to_id = {_norm_key(mod.get("name", "")): mod.get("id") for mod in hideout_modules}

    for raw_key, raw_level in input_levels.items():
        key = _norm_key(raw_key)
        alias_id = HIDEOUT_ALIASES.get(key)
        by_name_id = name_to_id.get(key)
        module_id = alias_id or by_name_id or raw_key

        try:
            level_num = int(raw_level)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid hideout level for '{raw_key}': {raw_level}") from None
        if level_num < 0:
            raise ValueError(f"Invalid hideout level for '{raw_key}': {raw_level}")

        out[module_id] = level_num

    return out


def _normalize_quest_name(value: str) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("\u2019", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def group_quests_by_trader(quests: list[dict]) -> dict[str, list[dict]]:
    quests_by_trader: dict[str, list[dict]] = {}
    for quest in quests:
        trader = quest.get("trader") or "Unknown"
        quests_by_trader.setdefault(trader, []).append(quest)

    for trader, quests_list in quests_by_trader.items():
        quests_list.sort(key=lambda q: q.get("sortOrder") or 0)

    return quests_by_trader


def build_quest_index(
    quests_by_trader: dict[str, list[dict]],
) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_name: dict[str, dict] = {}

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
    active_list: list[str], quest_index: tuple[dict[str, dict], dict[str, dict]]
) -> tuple[list[dict], list[str]]:
    by_id, by_name = quest_index
    resolved: list[dict] = []
    missing: list[str] = []

    for entry in active_list:
        by_id_match = by_id.get(entry)
        by_name_match = by_name.get(_normalize_quest_name(entry))
        found = by_id_match or by_name_match
        if found:
            resolved.append({
                "id": found.get("id"),
                "name": found.get("name"),
                "trader": found.get("trader"),
                "index": found.get("index"),
            })
        else:
            missing.append(entry)

    return resolved, missing
