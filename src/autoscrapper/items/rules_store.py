from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from ..config import has_saved_progress, load_progress_settings
from ..progress.rules_generator import generate_rules_from_active

DEFAULT_RULES_PATH = Path(__file__).with_name("items_rules.default.json")
CUSTOM_RULES_PATH = Path(__file__).with_name("items_rules.custom.json")
RULES_VERSION = 2


def active_rules_path() -> Path:
    return CUSTOM_RULES_PATH if CUSTOM_RULES_PATH.exists() else DEFAULT_RULES_PATH


def using_custom_rules() -> bool:
    return CUSTOM_RULES_PATH.exists()


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_overrides(raw: object) -> bool:
    return isinstance(raw, dict) and raw.get("version") == RULES_VERSION


def legacy_rules_pending() -> bool:
    return CUSTOM_RULES_PATH.exists() and not _is_overrides(_read(CUSTOM_RULES_PATH))


def _coerce_payload(raw: object) -> dict:
    if isinstance(raw, dict):
        items = raw.get("items")
        metadata = raw.get("metadata")
        return {
            "metadata": metadata if isinstance(metadata, dict) else {},
            "items": items if isinstance(items, list) else [],
        }
    return {"metadata": {}, "items": raw if isinstance(raw, list) else []}


def normalize_action(value: str) -> Optional[str]:
    return {
        "k": "keep",
        "keep": "keep",
        "s": "sell",
        "sell": "sell",
        "r": "recycle",
        "recycle": "recycle",
    }.get(value.strip().lower())


def _action(item: dict) -> str | None:
    aliases = {
        "your_call": "keep",
        "your call": "keep",
        "crafting material": "keep",
        "sell_or_recycle": "sell",
        "sell or recycle": "sell",
    }
    values = [item.get("action")]
    decisions = item.get("decision")
    if isinstance(decisions, list):
        values.extend(decisions)
    for raw in values:
        if isinstance(raw, str):
            action = raw.strip().lower()
            if action in {"keep", "sell", "recycle"}:
                return action
            if action in aliases:
                return aliases[action]
    return None


def rules_key(item: dict) -> str:
    item_id = str(item.get("id") or "").strip().lower()
    if item_id:
        return f"id:{item_id}"
    return f"name:{str(item.get('name') or '').strip().lower()}"


def _name_key(item: dict) -> str:
    return rules_key({"name": item.get("name")})


def _document() -> dict:
    if not CUSTOM_RULES_PATH.exists():
        return {"version": RULES_VERSION, "base": "default", "overrides": []}
    raw = _read(CUSTOM_RULES_PATH)
    if not _is_overrides(raw):
        raise ValueError("Review existing custom rules before updating them.")
    if raw.get("base") not in {"default", "progress"} or not isinstance(
        raw.get("overrides"), list
    ):
        raise ValueError("Invalid custom rule overrides.")
    return raw


def load_base_rules(base: str | None = None) -> dict:
    if base is None:
        if legacy_rules_pending():
            base = (
                "progress"
                if has_saved_progress(load_progress_settings())
                else "default"
            )
        else:
            base = _document()["base"]
    if base == "default":
        return load_rules(DEFAULT_RULES_PATH)
    if base != "progress":
        raise ValueError(f"Unknown rules base: {base}")
    settings = load_progress_settings()
    return generate_rules_from_active(
        settings.active_quests,
        settings.hideout_levels,
        completed_quests_override=settings.completed_quests,
    )


def _apply_overrides(base: dict, overrides: list[dict]) -> dict:
    by_key = {rules_key(item): item for item in overrides}
    used = set()
    items = []
    for item in base["items"]:
        key = rules_key(item)
        match_key = key if key in by_key else _name_key(item)
        override = by_key.get(match_key)
        if override is None:
            items.append(dict(item))
            continue
        used.add(match_key)
        action = override.get("action")
        if action is not None:
            items.append({**item, "action": action})
    for key, override in by_key.items():
        # ID overrides remain dormant when their item leaves the dataset.
        if (
            key not in used
            and not override.get("id")
            and override.get("action") is not None
        ):
            items.append(dict(override))
    return {"metadata": {**base["metadata"], "itemCount": len(items)}, "items": items}


def load_rules(path: Optional[Path] = None) -> dict:
    if path is not None and path != CUSTOM_RULES_PATH:
        return (
            _coerce_payload(_read(path))
            if path.exists()
            else {"metadata": {}, "items": []}
        )
    if not CUSTOM_RULES_PATH.exists():
        return load_rules(DEFAULT_RULES_PATH)
    raw = _read(CUSTOM_RULES_PATH)
    if not _is_overrides(raw):
        return _coerce_payload(raw)
    doc = _document()
    return _apply_overrides(load_base_rules(doc["base"]), doc["overrides"])


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as fp:
            temp_path = Path(fp.name)
            json.dump(payload, fp, indent=2)
            fp.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _override(item: dict, action: str | None) -> dict:
    entry = {"name": str(item.get("name") or "").strip(), "action": action}
    if item.get("id"):
        entry["id"] = item["id"]
    return entry


def set_rule_action(item: dict, action: str | None) -> None:
    doc = _document()
    if action is not None:
        normalized = normalize_action(action)
        if normalized is None:
            raise ValueError(f"Invalid action: {action}")
        action = normalized
    if not str(item.get("name") or "").strip():
        raise ValueError("A rule needs an item name.")
    base_items = load_base_rules(doc["base"])["items"]
    match = next(
        (entry for entry in base_items if rules_key(entry) == rules_key(item)), None
    )
    if match is None and not item.get("id"):
        match = next(
            (entry for entry in base_items if _name_key(entry) == _name_key(item)), None
        )
    target = match or item
    variants = [entry for entry in base_items if _name_key(entry) == _name_key(target)]
    keys = {rules_key(target), rules_key(item), _name_key(target)} | {
        rules_key(entry) for entry in variants
    }
    if len(variants) > 1:
        target = {"name": target["name"]}
    doc["overrides"] = [
        entry for entry in doc["overrides"] if rules_key(entry) not in keys
    ]
    if action is not None or match is not None:
        doc["overrides"].append(_override(target, action))
    _write_json(doc, CUSTOM_RULES_PATH)


def clear_rule_override(item: dict) -> None:
    doc = _document()
    keys = {rules_key(item), _name_key(item)} | {
        rules_key(entry)
        for entry in load_base_rules(doc["base"])["items"]
        if _name_key(entry) == _name_key(item)
    }
    doc["overrides"] = [
        entry for entry in doc["overrides"] if rules_key(entry) not in keys
    ]
    _write_json(doc, CUSTOM_RULES_PATH)


def is_rule_overridden(item: dict) -> bool:
    return bool({rules_key(item), _name_key(item)} & rule_override_keys())


def rule_override_keys() -> set[str]:
    if legacy_rules_pending():
        return set()
    return {rules_key(entry) for entry in _document()["overrides"]}


def use_progress_rules() -> dict:
    doc = _document()
    base = load_base_rules("progress")
    doc["base"] = "progress"
    _write_json(doc, CUSTOM_RULES_PATH)
    return _apply_overrides(base, doc["overrides"])


def reset_rules() -> None:
    CUSTOM_RULES_PATH.unlink(missing_ok=True)


@dataclass(frozen=True)
class MigrationChange:
    key: str
    name: str
    before_action: str | None
    after_action: str | None
    item: dict
    before_item: dict | None = None


@dataclass(frozen=True)
class RuleMigration:
    base: str
    base_payload: dict
    legacy_payload: dict
    changes: list[MigrationChange]
    legacy_bytes: bytes


def build_rule_migration(base: str | None = None) -> RuleMigration:
    legacy_bytes = CUSTOM_RULES_PATH.read_bytes()
    raw = json.loads(legacy_bytes)
    if _is_overrides(raw):
        raise ValueError("Custom rules have already been updated.")
    legacy = _coerce_payload(raw)
    base = base or (
        "progress" if has_saved_progress(load_progress_settings()) else "default"
    )
    generated = load_base_rules(base)
    # The scanner uses the last rule for each name in legacy files.
    legacy_by_name = {
        _name_key(item): item
        for item in legacy["items"]
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].strip()
        and _action(item) is not None
    }
    legacy_by_key = {rules_key(item): item for item in legacy_by_name.values()}
    generated_by_name = {}
    for item in generated["items"]:
        name_key = _name_key(item)
        if name_key in generated_by_name:
            # One scanner name needs one migration choice for all its variants.
            item = {
                "name": item["name"],
                "action": _action(item),
                "analysis": item.get("analysis", []),
            }
        generated_by_name[name_key] = item
    matched_names = set()
    changes = []
    for item in generated_by_name.values():
        old = legacy_by_key.get(rules_key(item))
        if old is None:
            candidate = legacy_by_name.get(_name_key(item))
            if candidate is not None:
                old = candidate
        before = _action(old) if old is not None else None
        if old is not None:
            matched_names.add(_name_key(old))
        after = _action(item)
        if before != after:
            changes.append(
                MigrationChange(rules_key(item), item["name"], before, after, item, old)
            )
    for name_key, item in legacy_by_name.items():
        if name_key not in matched_names and _action(item) is not None:
            # Retaining an item absent from the current dataset makes it a
            # user-added name rule, rather than reviving an obsolete item ID.
            custom_item = {"name": item["name"]}
            changes.append(
                MigrationChange(
                    name_key, item["name"], _action(item), None, custom_item, item
                )
            )
    changes.sort(key=lambda change: change.name.lower())
    return RuleMigration(base, generated, legacy, changes, legacy_bytes)


def complete_rule_migration(migration: RuleMigration, selected_keys: set[str]) -> None:
    if CUSTOM_RULES_PATH.read_bytes() != migration.legacy_bytes:
        raise ValueError("Custom rules changed. Reopen the review before applying it.")
    backup = CUSTOM_RULES_PATH.with_suffix(".legacy.json")
    # Never replace an earlier backup if a legacy file is restored later.
    suffix = 1
    while backup.exists():
        backup = CUSTOM_RULES_PATH.with_suffix(f".legacy-{suffix}.json")
        suffix += 1
    backup.write_bytes(migration.legacy_bytes)
    doc = {
        "version": RULES_VERSION,
        "base": migration.base,
        "overrides": [
            _override(change.item, change.before_action)
            for change in migration.changes
            if change.key in selected_keys
        ],
    }
    _write_json(doc, CUSTOM_RULES_PATH)
