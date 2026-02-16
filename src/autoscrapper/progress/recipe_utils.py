from __future__ import annotations

from typing import Dict, List


def build_reverse_recipe_index(items: List[dict]) -> Dict[str, List[str]]:
    """Build a reverse recipe index mapping ingredient IDs to output item IDs."""
    reverse_index: Dict[str, List[str]] = {}
    for item in items:
        recipe = item.get("recipe")
        if not isinstance(recipe, dict):
            continue
        for ingredient_id in recipe.keys():
            used_by = reverse_index.setdefault(ingredient_id, [])
            used_by.append(item.get("id", ""))
    return reverse_index
