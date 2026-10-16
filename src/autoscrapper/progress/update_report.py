from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


def _normalize_quest_name(value: object) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("’", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except TypeError, ValueError:
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
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _quest_requirement_ids(quest: Mapping[str, object]) -> List[str]:
    requirements = quest.get("requirements") or []
    return sorted(
        {
            requirement["item_id"]
            for requirement in requirements
            if isinstance(requirement, dict)
            and isinstance(requirement.get("item_id"), str)
            and requirement["item_id"]
        }
    )


def diff_quests(
    before_quests: Sequence[object], after_quests: Sequence[object]
) -> dict:
    before_by_id: Dict[str, Mapping[str, object]] = {}
    after_by_id: Dict[str, Mapping[str, object]] = {}

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
        }
        for quest_id in added_ids
    ]

    removed = [
        {
            "id": quest_id,
            "name": before_by_id[quest_id].get("name"),
            "trader": before_by_id[quest_id].get("trader"),
            "sortOrder": before_by_id[quest_id].get("sortOrder"),
        }
        for quest_id in removed_ids
    ]

    changed: List[dict] = []
    changed_fields = (
        "name",
        "trader",
        "sortOrder",
    )
    for quest_id in common_ids:
        before = before_by_id[quest_id]
        after = after_by_id[quest_id]
        changes: Dict[str, dict] = {}
        for field in changed_fields:
            if before.get(field) != after.get(field):
                changes[field] = {
                    "before": before.get(field),
                    "after": after.get(field),
                }
        before_requirements = _quest_requirement_ids(before)
        after_requirements = _quest_requirement_ids(after)
        if before_requirements != after_requirements:
            changes["requirements"] = {
                "before": before_requirements,
                "after": after_requirements,
            }
        if not changes:
            continue
        changed.append(
            {
                "id": quest_id,
                "name": after.get("name") or before.get("name"),
                "changes": changes,
            }
        )

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


def diff_rules(
    before_payload: Mapping[str, object], after_payload: Mapping[str, object]
) -> dict:
    before_items_raw = before_payload.get("items")
    after_items_raw = after_payload.get("items")
    before_items = before_items_raw if isinstance(before_items_raw, list) else []
    after_items = after_items_raw if isinstance(after_items_raw, list) else []

    before_by_key: Dict[str, Mapping[str, object]] = {}
    after_by_key: Dict[str, Mapping[str, object]] = {}

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
            "id": after_by_key[key].get("id"),
            "name": after_by_key[key].get("name"),
            "value": after_by_key[key].get("value"),
            "action": after_by_key[key].get("action"),
        }
        for key in added_keys
    ]

    removed = [
        {
            "id": before_by_key[key].get("id"),
            "name": before_by_key[key].get("name"),
            "value": before_by_key[key].get("value"),
            "action": before_by_key[key].get("action"),
        }
        for key in removed_keys
    ]

    modified: List[dict] = []
    value_changed: List[dict] = []
    action_changed: List[dict] = []
    analysis_changed: List[dict] = []
    name_changed: List[dict] = []

    for key in common_keys:
        before = before_by_key[key]
        after = after_by_key[key]
        changes: Dict[str, dict] = {}

        if before.get("value") != after.get("value"):
            change = {"before": before.get("value"), "after": after.get("value")}
            changes["value"] = change
            value_changed.append(
                {
                    "id": after.get("id") or before.get("id"),
                    "name": after.get("name") or before.get("name"),
                    **change,
                }
            )

        if before.get("action") != after.get("action"):
            change = {"before": before.get("action"), "after": after.get("action")}
            changes["action"] = change
            action_changed.append(
                {
                    "id": after.get("id") or before.get("id"),
                    "name": after.get("name") or before.get("name"),
                    **change,
                }
            )

        before_analysis = (
            before.get("analysis") if isinstance(before.get("analysis"), list) else []
        )
        after_analysis = (
            after.get("analysis") if isinstance(after.get("analysis"), list) else []
        )
        if before_analysis != after_analysis:
            changes["analysis"] = {"before": before_analysis, "after": after_analysis}
            analysis_changed.append(
                {
                    "id": after.get("id") or before.get("id"),
                    "name": after.get("name") or before.get("name"),
                }
            )

        if before.get("name") != after.get("name"):
            change = {"before": before.get("name"), "after": after.get("name")}
            changes["name"] = change
            name_changed.append(
                {
                    "id": after.get("id") or before.get("id"),
                    **change,
                }
            )

        if changes:
            modified.append(
                {
                    "id": after.get("id") or before.get("id"),
                    "name": after.get("name") or before.get("name"),
                    "changes": changes,
                }
            )

    modified.sort(
        key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id")))
    )
    value_changed.sort(
        key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id")))
    )
    action_changed.sort(
        key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id")))
    )
    analysis_changed.sort(
        key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id")))
    )
    name_changed.sort(
        key=lambda entry: (str(entry.get("name") or ""), str(entry.get("id")))
    )

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


def graph_gap_report(
    quests: Sequence[object], quest_graph: Mapping[str, object]
) -> dict:
    nodes = quest_graph.get("nodes")
    node_values = nodes.values() if isinstance(nodes, dict) else []
    node_names_normalized = {
        _normalize_quest_name(node_name)
        for node_name in node_values
        if _normalize_quest_name(node_name)
    }

    quest_entries = [quest for quest in quests if isinstance(quest, dict)]
    quest_names_normalized = {
        _normalize_quest_name(quest.get("name"))
        for quest in quest_entries
        if _normalize_quest_name(quest.get("name"))
    }

    missing_quests: List[dict] = []
    for quest in quest_entries:
        quest_name = _normalize_quest_name(quest.get("name"))
        if not quest_name or quest_name in node_names_normalized:
            continue
        missing_quests.append(
            {
                "id": quest.get("id"),
                "name": quest.get("name"),
                "trader": quest.get("trader"),
                "sortOrder": quest.get("sortOrder"),
            }
        )

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


def _render_item_list(
    items: Sequence[Mapping[str, object]], limit: int = 10
) -> List[str]:
    lines: List[str] = []
    for entry in list(items)[:limit]:
        item_id = entry.get("id") or "unknown-id"
        name = entry.get("name") or "Unknown"
        lines.append(f"- `{item_id}` ({name})")
    return lines


def build_markdown_summary(
    report: Mapping[str, object], *, sample_limit: int = 10
) -> str:
    snapshot = report.get("snapshot") or {}
    quests = report.get("quests") or {}
    rules = report.get("rules") or {}
    graph = report.get("questGraph") or {}
    assumptions = report.get("assumptions") or {}

    lines: List[str] = []
    lines.append("# Daily Metaforge Data Update Report")
    lines.append("")
    lines.append(f"Generated at: `{report.get('generatedAt', iso_now())}`")
    lines.append("")
    lines.append("## Snapshot")
    lines.append(
        "- Items: "
        f"{snapshot.get('beforeItemCount', 0)} -> {snapshot.get('afterItemCount', 0)}"
    )
    lines.append(
        "- Quests: "
        f"{snapshot.get('beforeQuestCount', 0)} -> {snapshot.get('afterQuestCount', 0)}"
    )
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
            lines.append(
                f"  - `{entry.get('id')}`: "
                f"`{entry.get('before')}` -> `{entry.get('after')}`"
            )

    value_changed = rules.get("valueChanged")
    if isinstance(value_changed, list) and value_changed:
        lines.append("- Value changes (sample):")
        for entry in value_changed[:sample_limit]:
            lines.append(
                f"  - `{entry.get('id')}`: "
                f"`{entry.get('before')}` -> `{entry.get('after')}`"
            )

    lines.append("")
    lines.append("## Quest Graph Coverage")
    missing_count = graph.get("questsMissingFromGraphCount", 0)
    lines.append("- Missing quests in `quests_graph.json`: " f"`{missing_count}`")
    if isinstance(missing_count, int) and missing_count > 0:
        lines.append(":warning: Graph drift detected. Solver fallback may be used.")
        missing_quests = graph.get("questsMissingFromGraph")
        if isinstance(missing_quests, list) and missing_quests:
            lines.append("- Missing quests (sample):")
            lines.extend(_render_item_list(missing_quests, limit=sample_limit))

    lines.append("")
    lines.append("## Generation Baseline")
    lines.append(
        "- `allQuestsCompleted`: " f"`{assumptions.get('allQuestsCompleted', False)}`"
    )
    lines.append(
        "- Workshop profile: " f"`{assumptions.get('workshopProfile', 'unknown')}`"
    )
    lines.append(
        "- Workshop IDs at level 2: "
        f"`{', '.join(assumptions.get('workshopIds', []))}`"
    )
    lines.append("- Report artifact: `artifacts/update-report.json`")

    lines.append("")
    lines.append(
        "This PR was generated automatically by the scheduled data update workflow."
    )

    return "\n".join(lines) + "\n"
