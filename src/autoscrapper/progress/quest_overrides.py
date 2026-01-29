from __future__ import annotations

from typing import List

QUEST_TRADER_OVERRIDES = {
    "combat-recon": "Shani",
    "bombing-run": "Shani",
    "on-deaf-ears": "Lance",
    "on-the-map": "Lance",
    "a-prime-specimen": "Shani",
}


def apply_quest_overrides(quests: List[dict]) -> List[dict]:
    """Apply quest overrides without mutating the original list."""
    updated = []
    for quest in quests:
        override_trader = QUEST_TRADER_OVERRIDES.get(quest.get("id"))
        if override_trader:
            updated.append({**quest, "trader": override_trader})
        else:
            updated.append(quest)
    return updated
