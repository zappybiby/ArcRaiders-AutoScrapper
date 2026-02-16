from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DEFAULT_RULES_PATH = Path(__file__).with_name("items_rules.default.json")
CUSTOM_RULES_PATH = Path(__file__).with_name("items_rules.custom.json")


def active_rules_path() -> Path:
    return CUSTOM_RULES_PATH if CUSTOM_RULES_PATH.exists() else DEFAULT_RULES_PATH


def using_custom_rules() -> bool:
    return CUSTOM_RULES_PATH.exists()


def _coerce_payload(raw: object) -> dict:
    if isinstance(raw, dict):
        items = raw.get("items")
        if not isinstance(items, list):
            items = []
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        return {"metadata": metadata, "items": items}

    if isinstance(raw, list):
        return {"metadata": {}, "items": raw}

    return {"metadata": {}, "items": []}


def load_rules(path: Optional[Path] = None) -> dict:
    rules_path = path or active_rules_path()
    if not rules_path.exists():
        return {"metadata": {}, "items": []}
    with rules_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return _coerce_payload(raw)


def save_rules(payload: dict, path: Path) -> None:
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    metadata = (
        payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    )
    metadata["itemCount"] = len(items)
    payload = {"metadata": metadata, "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def save_custom_rules(payload: dict) -> None:
    save_rules(payload, CUSTOM_RULES_PATH)


def normalize_action(value: str) -> Optional[str]:
    raw = value.strip().lower()
    if raw in {"k", "keep"}:
        return "keep"
    if raw in {"s", "sell"}:
        return "sell"
    if raw in {"r", "recycle"}:
        return "recycle"
    return None
