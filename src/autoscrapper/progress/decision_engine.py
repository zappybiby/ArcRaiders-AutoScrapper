from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .recipe_utils import build_reverse_recipe_index
from .weapon_grouping import WeaponGrouper


@dataclass(frozen=True)
class DecisionReason:
    decision: str
    reasons: List[str]
    dependencies: Optional[List[str]] = None
    recycle_value_exceeds_item: bool = False


@dataclass(frozen=True)
class CraftingValue:
    is_valuable: bool
    recipe_count: int
    details: str


@dataclass(frozen=True)
class RecycleValue:
    is_valuable: bool
    description: str
    estimated_value: int


class DecisionEngine:
    def __init__(
        self,
        items: List[dict],
        hideout_modules: List[dict],
        quests: List[dict],
        projects: List[dict],
    ) -> None:
        self.items = {item.get("id"): item for item in items}
        self.hideout_modules = hideout_modules
        self.quests = quests
        self.projects = projects
        self.reverse_recipe_index = build_reverse_recipe_index(items)

    def finalize_decision(self, item: dict, decision: DecisionReason) -> DecisionReason:
        final_decision = decision
        recycle_data = item.get("recyclesInto") or item.get("salvagesInto") or item.get(
            "crafting"
        )
        if recycle_data and isinstance(recycle_data, dict) and recycle_data:
            recycle_value = self.evaluate_recycle_value(item)
            if recycle_value.estimated_value > item.get("value", 0):
                final_decision = DecisionReason(
                    decision=final_decision.decision,
                    reasons=final_decision.reasons,
                    dependencies=final_decision.dependencies,
                    recycle_value_exceeds_item=True,
                )

        if final_decision.decision == "situational":
            final_decision = DecisionReason(
                decision="keep",
                reasons=final_decision.reasons
                + ["Override: treat 'Your Call' as Keep"],
                dependencies=final_decision.dependencies,
                recycle_value_exceeds_item=final_decision.recycle_value_exceeds_item,
            )

        return final_decision

    def get_decision(self, item: dict, user_progress: dict) -> DecisionReason:
        item_type = str(item.get("type", "")).lower()
        rarity = str(item.get("rarity", "")).lower()

        if item.get("id") in {"assorted-seeds", "assorted_seeds"}:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="keep",
                    reasons=[
                        "Valuable currency item",
                        "Used for trading with Celeste",
                    ],
                ),
            )

        if rarity == "legendary":
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="keep",
                    reasons=["Legendary rarity - extremely valuable", "Keep all legendaries"],
                ),
            )

        if item_type == "blueprint":
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        "Blueprint - valuable for unlocking crafting recipes",
                        "Review carefully before selling or recycling",
                    ],
                ),
            )

        if item_type == "weapon" or WeaponGrouper.is_weapon_variant(item):
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        "Weapon - review based on your current loadout",
                        "Consider tier and your play style",
                    ],
                ),
            )

        if item_type == "ammunition":
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        "Ammunition - essential for weapons",
                        "Review based on your weapon loadout",
                    ],
                ),
            )

        if item_type in {"quick use", "quick_use"}:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        "Consumable item - grenades, healing items, etc.",
                        "Review based on your current inventory needs",
                    ],
                ),
            )

        if item_type == "key":
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        "Key - opens locked areas and containers",
                        "Review based on areas you want to access",
                    ],
                ),
            )

        quest_use = self.is_used_in_active_quests(item, user_progress)
        if quest_use["is_used"]:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="keep",
                    reasons=[
                        f"Required for quest: {', '.join(quest_use['quest_names'])}"
                    ],
                    dependencies=quest_use["quest_names"],
                ),
            )

        project_use = self.is_used_in_active_projects(item, user_progress)
        if project_use["is_used"]:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="keep",
                    reasons=[
                        f"Needed for project: {', '.join(project_use['project_names'])}"
                    ],
                    dependencies=project_use["project_names"],
                ),
            )

        upgrade_use = self.is_needed_for_upgrades(item, user_progress)
        if upgrade_use["is_needed"]:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="keep",
                    reasons=[
                        "Required for hideout upgrade: "
                        + ", ".join(upgrade_use["module_names"])
                    ],
                    dependencies=upgrade_use["module_names"],
                ),
            )

        crafting_value = self.evaluate_crafting_value(item)
        if crafting_value.is_valuable:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        f"Used in {crafting_value.recipe_count} crafting recipes",
                        crafting_value.details,
                    ],
                ),
            )

        if self.is_high_value_trinket(item):
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="sell_or_recycle",
                    reasons=[
                        f"High value ({item.get('value', 0)} coins)",
                        "No crafting or upgrade use",
                    ],
                ),
            )

        recycle_data = item.get("recyclesInto") or item.get("salvagesInto") or item.get(
            "crafting"
        )
        if recycle_data and isinstance(recycle_data, dict) and recycle_data:
            recycle_value = self.evaluate_recycle_value(item)
            if recycle_value.is_valuable:
                compare = (
                    "worth MORE than"
                    if recycle_value.estimated_value > item.get("value", 0)
                    else "worth less than"
                )
                return self.finalize_decision(
                    item,
                    DecisionReason(
                        decision="sell_or_recycle",
                        reasons=[
                            f"Recycles into: {recycle_value.description}",
                            "Recycle value: Components "
                            f"({recycle_value.estimated_value} coins) {compare} Item "
                            f"({item.get('value', 0)} coins)",
                        ],
                    ),
                )

        if rarity in {"rare", "epic"}:
            return self.finalize_decision(
                item,
                DecisionReason(
                    decision="situational",
                    reasons=[
                        f"{rarity.title()} rarity",
                        "May have future use - review carefully",
                    ],
                ),
            )

        return self.finalize_decision(
            item,
            DecisionReason(
                decision="sell_or_recycle",
                reasons=["No immediate use found", "Safe to sell or recycle"],
            ),
        )

    def is_used_in_active_quests(self, item: dict, user_progress: dict) -> Dict[str, List[str] | bool]:
        quest_names: List[str] = []
        completed = set(user_progress.get("completedQuests", []))
        for quest in self.quests:
            if quest.get("id") in completed:
                continue

            is_required = False
            requirements = quest.get("requirements") or []
            if isinstance(requirements, list):
                is_required = any(req.get("item_id") == item.get("id") for req in requirements)

            reward_items = quest.get("rewardItemIds") or []
            if not is_required and isinstance(reward_items, list):
                is_required = any(
                    reward.get("item_id") == item.get("id") for reward in reward_items
                )

            if is_required:
                quest_names.append(quest.get("name", ""))

        return {"is_used": bool(quest_names), "quest_names": quest_names}

    def is_used_in_active_projects(
        self, item: dict, user_progress: dict
    ) -> Dict[str, List[str] | bool]:
        project_names: List[str] = []
        completed = set(user_progress.get("completedProjects", []))

        for project in self.projects:
            if project.get("id") in completed:
                continue

            is_required = False
            requirements = project.get("requirements") or []
            if isinstance(requirements, list):
                is_required = any(req.get("item_id") == item.get("id") for req in requirements)

            phases = project.get("phases") or []
            if not is_required and isinstance(phases, list):
                for phase in phases:
                    reqs = phase.get("requirementItemIds") or []
                    if isinstance(reqs, list) and any(
                        req.get("item_id") == item.get("id") for req in reqs
                    ):
                        is_required = True
                        break

            if is_required:
                project_names.append(project.get("name", ""))

        return {"is_used": bool(project_names), "project_names": project_names}

    def is_needed_for_upgrades(self, item: dict, user_progress: dict) -> Dict[str, List[str] | bool]:
        module_names: List[str] = []
        hideout_levels = user_progress.get("hideoutLevels", {})

        for module in self.hideout_modules:
            module_id = module.get("id")
            current_level = hideout_levels.get(module_id, 0)
            max_level = module.get("maxLevel", 0)
            levels = module.get("levels") or []
            if current_level >= max_level:
                continue
            if not isinstance(levels, list):
                continue

            for level_data in levels:
                level = level_data.get("level")
                if level is None or level <= current_level:
                    continue
                reqs = level_data.get("requirementItemIds") or []
                if not isinstance(reqs, list):
                    continue
                is_required = any(req.get("item_id") == item.get("id") for req in reqs)
                if is_required:
                    module_names.append(f"{module.get('name')} (Level {level})")

        return {"is_needed": bool(module_names), "module_names": module_names}

    def evaluate_crafting_value(self, item: dict) -> CraftingValue:
        recipe_count = len(self.reverse_recipe_index.get(item.get("id"), []))
        rarity = str(item.get("rarity", "")).lower()
        is_rare = rarity in {"rare", "epic", "legendary"}
        return CraftingValue(
            is_valuable=recipe_count > 2 or (recipe_count > 0 and is_rare),
            recipe_count=recipe_count,
            details="Rare crafting material" if is_rare else "Common crafting ingredient",
        )

    def is_high_value_trinket(self, item: dict) -> bool:
        high_value_threshold = 1000
        trinket_keywords = {"trinket", "misc", "collectible"}

        has_no_recipe = not item.get("recipe")
        recycle_data = item.get("recyclesInto") or item.get("salvagesInto") or item.get(
            "crafting"
        )
        has_no_recycle = not recycle_data
        item_type = str(item.get("type", "")).lower()
        is_trinket = any(keyword in item_type for keyword in trinket_keywords)

        return (
            item.get("value", 0) >= high_value_threshold
            and has_no_recipe
            and has_no_recycle
            and is_trinket
        )

    def evaluate_recycle_value(self, item: dict) -> RecycleValue:
        recycle_data = item.get("recyclesInto") or item.get("salvagesInto") or item.get(
            "crafting"
        )
        if not recycle_data or not isinstance(recycle_data, dict) or not recycle_data:
            return RecycleValue(is_valuable=False, description="Nothing", estimated_value=0)

        materials = []
        total_value = 0

        for item_id, quantity in recycle_data.items():
            output_item = self.items.get(item_id)
            if output_item:
                materials.append(f"{quantity}x {output_item.get('name')}")
                try:
                    total_value += int(output_item.get("value", 0)) * int(quantity)
                except (TypeError, ValueError):
                    continue

        return RecycleValue(
            is_valuable=total_value > item.get("value", 0) * 0.5,
            description=", ".join(materials),
            estimated_value=total_value,
        )

    def get_items_with_decisions(self, user_progress: dict) -> List[dict]:
        items_with_decisions: List[dict] = []
        for item in self.items.values():
            decision = self.get_decision(item, user_progress)
            items_with_decisions.append({**item, "decision_data": decision})
        return items_with_decisions
