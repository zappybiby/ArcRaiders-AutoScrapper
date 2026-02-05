from __future__ import annotations

"""Compute user-facing rule diffs between default and updated item payloads.

Both payloads are expected to contain an ``items`` list of dict-like entries.
Entries are matched by ``id`` first, then by ``name`` as a fallback.
Only action changes are emitted.
"""

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RuleChange:
    item_id: str
    name: str
    before_action: str
    after_action: str
    reasons: list[str]


def _normalize_key(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized:
            return normalized
    return None


def _first_nonempty_text(value: object) -> str | None:
    if isinstance(value, str):
        return _normalize_key(value)
    if isinstance(value, list):
        for entry in value:
            normalized = _normalize_key(entry)
            if normalized:
                return normalized
    return None


def _extract_action(item: Mapping[str, object]) -> str | None:
    return _first_nonempty_text(item.get("action")) or _first_nonempty_text(
        item.get("decision")
    )


def _extract_reasons(item: Mapping[str, object]) -> list[str]:
    reasons_raw = item.get("analysis")
    reasons: list[str] = []
    if isinstance(reasons_raw, list):
        for reason in reasons_raw:
            if isinstance(reason, str) and reason.strip():
                reasons.append(reason.strip())
    return reasons


def _build_default_indexes(
    items: list[object],
) -> tuple[dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    by_id: dict[str, Mapping[str, object]] = {}
    by_name: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = _normalize_key(item.get("id"))
        if item_id:
            by_id[item_id] = item
        name = _normalize_key(item.get("name"))
        if name:
            by_name[name] = item
    return by_id, by_name


def _match_default_item(
    updated_item: Mapping[str, object],
    default_by_id: Mapping[str, Mapping[str, object]],
    default_by_name: Mapping[str, Mapping[str, object]],
) -> Mapping[str, object] | None:
    item_id = _normalize_key(updated_item.get("id"))
    if item_id:
        default_item = default_by_id.get(item_id)
        if default_item is not None:
            return default_item
    name = _normalize_key(updated_item.get("name"))
    if not name:
        return None
    return default_by_name.get(name)


def collect_rule_changes(
    default_payload: Mapping[str, object], updated_payload: Mapping[str, object]
) -> list[RuleChange]:
    default_items = default_payload.get("items")
    updated_items = updated_payload.get("items")
    if not isinstance(default_items, list) or not isinstance(updated_items, list):
        return []

    default_by_id, default_by_name = _build_default_indexes(default_items)
    changes: list[RuleChange] = []

    for updated_item in updated_items:
        if not isinstance(updated_item, dict):
            continue
        default_item = _match_default_item(updated_item, default_by_id, default_by_name)
        if default_item is None:
            continue

        before_action = _extract_action(default_item)
        after_action = _extract_action(updated_item)
        if (
            before_action is None
            or after_action is None
            or before_action == after_action
        ):
            continue

        reasons = _extract_reasons(updated_item)
        item_id = updated_item.get("id") or default_item.get("id") or ""
        name = updated_item.get("name") or default_item.get("name") or item_id
        changes.append(
            RuleChange(
                item_id=str(item_id),
                name=str(name),
                before_action=before_action,
                after_action=after_action,
                reasons=reasons,
            )
        )

    changes.sort(key=lambda change: change.name.lower())
    return changes
