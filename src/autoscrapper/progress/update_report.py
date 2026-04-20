from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

import orjson


def _normalize_quest_name(value: object) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("\u2019", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _item_key(item: Mapping[str, object]) -> str:
    item_id = _normalize_text(item.get("id"))
    if item_id:
        return f"id:{item_id}"
    name = _normalize_text(item.get("name"))
    if name:
        return f"name:{name.lower()}"
    return ""


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return orjson.loads(path.read_bytes())
    except orjson.JSONDecodeError:
        return default


def diff_quests(before_quests: Sequence[object], after_quests: Sequence[object]) -> dict:
    before_by_id: dict[str, Mapping[str, object]] = {}
    after_by_id: dict[str, Mapping[str, object]] = {}

    for quest in before_quests:
        if not isinstance(quest, dict):
            continue
        quest_id = _normalize_text(quest.get("id"))
        if quest_id:
            before_by_id[quest_id] = quest

    for quest in after_quests:
        if not isinstance(quest, dict):
            continue
        quest_id = _normalize_text(quest.get("id"))
        if quest_id:
            after_by_id[quest_id] = quest

    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())

    added_ids = sorted(after_ids - before_ids)
    removed_ids = sorted(before_ids - after_ids)
    common_ids = sorted(before_ids & after_ids)

    added = [
        {
            "id": quest_id,
            "name": after_by_id[quest_id].get("name"),
            "trader": after_by_id[quest_id].get("trader"),
            "sortOrder": after_by_id[quest_id].get("sortOrder"),
            "xp": after_by_id[quest_id].get("xp"),
        }
        for quest_id in added_ids
    ]

    removed = [
        {
            "id": quest_id,
            "name": before_by_id[quest_id].get("name"),
            "trader": before_by_id[quest_id].get("trader"),
            "sortOrder": before_by_id[quest_id].get("sortOrder"),
            "xp": before_by_id[quest_id].get("xp"),
        }
        for quest_id in removed_ids
    ]

    changed: list[dict] = []
    changed_fields = (
        "name",
        "trader",
        "sortOrder",
        "xp",
        "requirements",
        "rewardItemIds",
    )
    for quest_id in common_ids:
        before = before_by_id[quest_id]
        after = after_by_id[quest_id]
        changes: dict[str, dict] = {}
        for field in changed_fields:
            before_val = before.get(field)
            after_val = after.get(field)
            if before_val != after_val:
                changes[field] = {
                    "before": before_val,
                    "after": after_val,
                }
        if not changes:
            continue
        changed.append({
            "id": quest_id,
            "name": after.get("name") or before.get("name"),
            "changes": changes,
        })

    changed.sort(key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id"))))

    return {
        "beforeCount": len(before_by_id),
        "afterCount": len(after_by_id),
        "addedCount": len(added),
        "removedCount": len(removed),
        "changedCount": len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def diff_rules(before_payload: Mapping[str, object], after_payload: Mapping[str, object]) -> dict:
    before_items_raw = before_payload.get("items")
    after_items_raw = after_payload.get("items")
    before_items = before_items_raw if isinstance(before_items_raw, list) else []
    after_items = after_items_raw if isinstance(after_items_raw, list) else []

    before_by_key: dict[str, Mapping[str, object]] = {}
    after_by_key: dict[str, Mapping[str, object]] = {}

    for item in before_items:
        if not isinstance(item, dict):
            continue
        key = _item_key(item)
        if key:
            before_by_key[key] = item

    for item in after_items:
        if not isinstance(item, dict):
            continue
        key = _item_key(item)
        if key:
            after_by_key[key] = item

    before_keys = set(before_by_key.keys())
    after_keys = set(after_by_key.keys())
    common_keys = sorted(before_keys & after_keys)
    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)

    added = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "value": item.get("value"),
            "action": item.get("action"),
        }
        for key in added_keys
        if (item := after_by_key[key]) or True
    ]

    removed = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "value": item.get("value"),
            "action": item.get("action"),
        }
        for key in removed_keys
        if (item := before_by_key[key]) or True
    ]

    modified: list[dict] = []
    value_changed: list[dict] = []
    action_changed: list[dict] = []
    analysis_changed: list[dict] = []
    name_changed: list[dict] = []

    for key in common_keys:
        before = before_by_key[key]
        after = after_by_key[key]
        changes: dict[str, dict] = {}

        before_value = before.get("value")
        after_value = after.get("value")
        before_action = before.get("action")
        after_action = after.get("action")
        before_analysis_raw = before.get("analysis")
        after_analysis_raw = after.get("analysis")
        before_name = before.get("name")
        after_name = after.get("name")

        # Cache IDs and Names for changes
        after_id_or_before = after.get("id") or before.get("id")
        after_name_or_before = after_name or before_name

        if before_value != after_value:
            change = {"before": before_value, "after": after_value}
            changes["value"] = change
            value_changed.append({
                "id": after_id_or_before,
                "name": after_name_or_before,
                **change,
            })

        if before_action != after_action:
            change = {"before": before_action, "after": after_action}
            changes["action"] = change
            action_changed.append({
                "id": after_id_or_before,
                "name": after_name_or_before,
                **change,
            })

        before_analysis = before_analysis_raw if isinstance(before_analysis_raw, list) else []
        after_analysis = after_analysis_raw if isinstance(after_analysis_raw, list) else []
        if before_analysis != after_analysis:
            changes["analysis"] = {"before": before_analysis, "after": after_analysis}
            analysis_changed.append({
                "id": after_id_or_before,
                "name": after_name_or_before,
            })

        if before_name != after_name:
            change = {"before": before_name, "after": after_name}
            changes["name"] = change
            name_changed.append({
                "id": after_id_or_before,
                **change,
            })

        if changes:
            modified.append({
                "id": after_id_or_before,
                "name": after_name_or_before,
                "changes": changes,
            })

    modified.sort(key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id"))))
    value_changed.sort(key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id"))))
    action_changed.sort(key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id"))))
    analysis_changed.sort(key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id"))))
    name_changed.sort(key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id"))))

    return {
        "beforeCount": len(before_by_key),
        "afterCount": len(after_by_key),
        "addedCount": len(added),
        "removedCount": len(removed),
        "modifiedCount": len(modified),
        "valueChangedCount": len(value_changed),
        "actionChangedCount": len(action_changed),
        "analysisChangedCount": len(analysis_changed),
        "nameChangedCount": len(name_changed),
        "added": added,
        "removed": removed,
        "modified": modified,
        "valueChanged": value_changed,
        "actionChanged": action_changed,
        "analysisChanged": analysis_changed,
        "nameChanged": name_changed,
    }


def graph_gap_report(quests: Sequence[object], quest_graph: Mapping[str, object]) -> dict:
    nodes = quest_graph.get("nodes")
    node_values = nodes.values() if isinstance(nodes, dict) else []
    node_names_normalized = {
        _normalize_quest_name(node_name) for node_name in node_values if _normalize_quest_name(node_name)
    }

    quest_entries = [quest for quest in quests if isinstance(quest, dict)]
    quest_names_normalized = {
        _normalize_quest_name(quest.get("name")) for quest in quest_entries if _normalize_quest_name(quest.get("name"))
    }

    missing_quests: list[dict] = []
    for quest in quest_entries:
        quest_name = _normalize_quest_name(quest.get("name"))
        if not quest_name or quest_name in node_names_normalized:
            continue
        missing_quests.append({
            "id": quest.get("id"),
            "name": quest.get("name"),
            "trader": quest.get("trader"),
            "sortOrder": quest.get("sortOrder"),
        })

    missing_quests.sort(
        key=lambda quest: (
            str(quest.get("trader") or ""),
            _safe_float(quest.get("sortOrder")),
            str(quest.get("name") or ""),
        )
    )

    orphaned_nodes = sorted(node_names_normalized - quest_names_normalized)

    return {
        "graphNodeCount": len(node_names_normalized),
        "questCount": len(quest_entries),
        "questsMissingFromGraphCount": len(missing_quests),
        "questsMissingFromGraph": missing_quests,
        "graphNodesMissingFromQuestsCount": len(orphaned_nodes),
        "graphNodesMissingFromQuests": orphaned_nodes,
    }


def _render_item_list(items: Sequence[Mapping[str, object]], limit: int = 10) -> list[str]:
    lines: list[str] = []
    for entry in list(items)[:limit]:
        item_id = entry.get("id") or "unknown-id"
        name = entry.get("name") or "Unknown"
        lines.append(f"- `{item_id}` ({name})")
    return lines


def build_markdown_summary(report: Mapping[str, Any], *, sample_limit: int = 10) -> str:
    snapshot = report.get("snapshot") or {}
    quests = report.get("quests") or {}
    rules = report.get("rules") or {}
    graph = report.get("questGraph") or {}
    assumptions = report.get("assumptions") or {}

    lines: list[str] = []
    lines.append("# Daily Metaforge Data Update Report")
    lines.append("")
    lines.append(f"Generated at: `{report.get('generatedAt', iso_now())}`")
    lines.append("")
    lines.append("## Snapshot")
    lines.append(f"- Items: {snapshot.get('beforeItemCount', 0)} -> {snapshot.get('afterItemCount', 0)}")
    lines.append(f"- Quests: {snapshot.get('beforeQuestCount', 0)} -> {snapshot.get('afterQuestCount', 0)}")
    lines.append(
        "- Data lastUpdated: "
        f"`{snapshot.get('beforeLastUpdated', 'unknown')}` -> "
        f"`{snapshot.get('afterLastUpdated', 'unknown')}`"
    )

    changed_files = snapshot.get("changedFiles")
    if isinstance(changed_files, list) and changed_files:
        lines.append("- Changed files:")
        lines.extend(f"  - `{path}`" for path in changed_files)
    else:
        lines.append("- Changed files: none")

    lines.append("")
    lines.append("## Quest Changes")
    lines.append(
        "- Counts: "
        f"added `{quests.get('addedCount', 0)}`, "
        f"removed `{quests.get('removedCount', 0)}`, "
        f"changed `{quests.get('changedCount', 0)}`"
    )

    added_quests = quests.get("added")
    if isinstance(added_quests, list) and added_quests:
        lines.append("- Added quests:")
        lines.extend(_render_item_list(added_quests, limit=sample_limit))

    removed_quests = quests.get("removed")
    if isinstance(removed_quests, list) and removed_quests:
        lines.append("- Removed quests:")
        lines.extend(_render_item_list(removed_quests, limit=sample_limit))

    lines.append("")
    lines.append("## Default Rules Diff")
    lines.append(
        "- Counts: "
        f"added `{rules.get('addedCount', 0)}`, "
        f"removed `{rules.get('removedCount', 0)}`, "
        f"modified `{rules.get('modifiedCount', 0)}`"
    )
    lines.append(
        "- Modified breakdown: "
        f"value `{rules.get('valueChangedCount', 0)}`, "
        f"action `{rules.get('actionChangedCount', 0)}`, "
        f"analysis `{rules.get('analysisChangedCount', 0)}`, "
        f"name `{rules.get('nameChangedCount', 0)}`"
    )

    added_rules = rules.get("added")
    if isinstance(added_rules, list) and added_rules:
        lines.append("- Added rule items:")
        lines.extend(_render_item_list(added_rules, limit=sample_limit))

    action_changed = rules.get("actionChanged")
    if isinstance(action_changed, list) and action_changed:
        lines.append("- Action changes (sample):")
        for entry in action_changed[:sample_limit]:
            lines.append(f"  - `{entry.get('id')}`: `{entry.get('before')}` -> `{entry.get('after')}`")

    value_changed = rules.get("valueChanged")
    if isinstance(value_changed, list) and value_changed:
        lines.append("- Value changes (sample):")
        for entry in value_changed[:sample_limit]:
            lines.append(f"  - `{entry.get('id')}`: `{entry.get('before')}` -> `{entry.get('after')}`")

    lines.append("")
    lines.append("## Quest Graph Coverage")
    missing_count = graph.get("questsMissingFromGraphCount", 0)
    lines.append(f"- Missing quests in `quests_graph.json`: `{missing_count}`")
    if isinstance(missing_count, int) and missing_count > 0:
        lines.append(":warning: Graph drift detected. Solver fallback may be used.")
        missing_quests = graph.get("questsMissingFromGraph")
        if isinstance(missing_quests, list) and missing_quests:
            lines.append("- Missing quests (sample):")
            lines.extend(_render_item_list(missing_quests, limit=sample_limit))

    lines.append("")
    lines.append("## Generation Baseline")
    lines.append(f"- `allQuestsCompleted`: `{assumptions.get('allQuestsCompleted', False)}`")
    lines.append(f"- Workshop profile: `{assumptions.get('workshopProfile', 'unknown')}`")
    lines.append(f"- Workshop IDs at level 2: `{', '.join(assumptions.get('workshopIds', []))}`")
    lines.append("- Report artifact: `artifacts/update-report.json`")

    lines.append("")
    lines.append("This PR was generated automatically by the scheduled data update workflow.")

    return "\n".join(lines) + "\n"
