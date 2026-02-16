from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .quest_overrides import apply_quest_overrides

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class GameData:
    items: List[dict]
    hideout_modules: List[dict]
    quests: List[dict]
    quest_graph: Dict[str, Any]
    projects: List[dict]
    metadata: Dict[str, str]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_game_data(data_dir: Optional[Path] = None) -> GameData:
    data_dir = data_dir or DATA_DIR

    items_path = data_dir / "items.json"
    quests_path = data_dir / "quests.json"
    quest_graph_path = data_dir / "quests_graph.json"
    hideout_modules_path = data_dir / "static" / "hideout_modules.json"
    projects_path = data_dir / "static" / "projects.json"
    metadata_path = data_dir / "metadata.json"
    price_overrides_path = data_dir / "price_overrides.json"

    if (
        not items_path.exists()
        or not quests_path.exists()
        or not quest_graph_path.exists()
    ):
        raise FileNotFoundError(
            "Missing data snapshot. Expected "
            f"{items_path}, {quests_path}, and {quest_graph_path}."
        )

    items = _read_json(items_path)
    quests = apply_quest_overrides(_read_json(quests_path))
    quest_graph = _read_json(quest_graph_path)
    hideout_modules = _read_json(hideout_modules_path)
    projects = _read_json(projects_path)

    metadata: Optional[dict] = None
    if metadata_path.exists():
        try:
            metadata = _read_json(metadata_path)
        except json.JSONDecodeError:
            metadata = None

    price_overrides: Optional[dict] = None
    if price_overrides_path.exists():
        try:
            price_overrides = _read_json(price_overrides_path)
        except json.JSONDecodeError:
            price_overrides = None

    items_with_overrides = _apply_price_overrides(items, price_overrides)
    normalized_items = _normalize_items(items_with_overrides)

    return GameData(
        items=normalized_items,
        hideout_modules=hideout_modules,
        quests=quests,
        quest_graph=quest_graph,
        projects=projects,
        metadata={
            "lastUpdated": (metadata or {}).get("lastUpdated", "1970-01-01T00:00:00Z"),
            "source": (metadata or {}).get("source", "unknown"),
            "version": (metadata or {}).get("version", "0.0.0"),
        },
    )


def _apply_price_overrides(
    items: List[dict], price_overrides: Optional[dict]
) -> List[dict]:
    if not price_overrides or not isinstance(price_overrides.get("overrides"), dict):
        return items
    overrides = price_overrides.get("overrides", {})
    out = []
    for item in items:
        override = overrides.get(item.get("id"))
        if override and isinstance(override, dict) and "value" in override:
            out.append({**item, "value": override["value"]})
        else:
            out.append(item)
    return out


def _normalize_items(items: List[dict]) -> List[dict]:
    normalized = []
    for item in items:
        found_in = item.get("foundIn")
        if isinstance(found_in, str):
            updated = {
                **item,
                "foundIn": [loc.strip() for loc in found_in.split(",") if loc.strip()],
            }
            normalized.append(updated)
        else:
            normalized.append(item)
    return normalized
