from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Dict, List, Set

from ...config import ProgressSettings, load_progress_settings, save_progress_settings
from ...progress.data_loader import load_game_data
from ...progress.progress_config import (
    build_quest_index,
    infer_completed_by_trader,
    resolve_active_quests,
)


@dataclass(frozen=True)
class QuestEntry:
    id: str
    name: str
    trader: str
    sort_order: int


@dataclass(frozen=True)
class HideoutModule:
    id: str
    name: str
    max_level: int


@dataclass
class ProgressWizardState:
    all_quests_completed: bool
    active_ids: Set[str]
    hideout_levels: Dict[str, int]
    quest_entries: List[QuestEntry]
    hideout_modules: List[HideoutModule]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_quest_value(value: str) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("’", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def build_quest_entries(quests: List[dict]) -> List[QuestEntry]:
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


def build_hideout_modules(hideout_modules: List[dict]) -> List[HideoutModule]:
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


def compute_completed_quests(
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


def build_wizard_state() -> ProgressWizardState:
    game_data = load_game_data()
    quest_entries = build_quest_entries(game_data.quests)
    hideout_modules = build_hideout_modules(game_data.hideout_modules)
    settings = load_progress_settings()

    return ProgressWizardState(
        all_quests_completed=settings.all_quests_completed,
        active_ids=set(settings.active_quests),
        hideout_levels=dict(settings.hideout_levels),
        quest_entries=quest_entries,
        hideout_modules=hideout_modules,
    )


def persist_progress_settings(
    *,
    all_quests_completed: bool,
    active_quests: List[str],
    completed_quests: List[str],
    hideout_levels: Dict[str, int],
) -> ProgressSettings:
    progress_settings = ProgressSettings(
        all_quests_completed=all_quests_completed,
        active_quests=sorted(active_quests),
        completed_quests=sorted(completed_quests),
        hideout_levels=hideout_levels,
        last_updated=iso_now(),
    )
    save_progress_settings(progress_settings)
    return progress_settings


def save_workshop_levels(levels: Dict[str, int]) -> None:
    settings = load_progress_settings()
    persist_progress_settings(
        all_quests_completed=settings.all_quests_completed,
        active_quests=settings.active_quests,
        completed_quests=settings.completed_quests,
        hideout_levels=levels,
    )
