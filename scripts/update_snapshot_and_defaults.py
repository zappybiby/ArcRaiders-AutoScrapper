#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13, <3.14"
# dependencies = ["orjson"]
# ///

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from collections.abc import Iterable

import orjson

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autoscrapper.progress.data_update import update_data_snapshot  # noqa: E402
from autoscrapper.api.client import ArcTrackerClient  # noqa: E402
from autoscrapper.progress.rules_generator import (  # noqa: E402
    generate_rules_from_active,
    write_rules,
)
from autoscrapper.progress.update_report import (  # noqa: E402
    build_markdown_summary,
    diff_quests,
    diff_rules,
    graph_gap_report,
    iso_now,
    load_json,
)

DATA_DIR = REPO_ROOT / "src" / "autoscrapper" / "progress" / "data"
DEFAULT_RULES_PATH = REPO_ROOT / "src" / "autoscrapper" / "items" / "items_rules.default.json"
TARGET_RELATIVE_FILES = (
    "src/autoscrapper/progress/data/items.json",
    "src/autoscrapper/progress/data/quests.json",
    "src/autoscrapper/progress/data/quests_by_trader.json",
    "src/autoscrapper/progress/data/metadata.json",
    "src/autoscrapper/items/items_rules.default.json",
)
EXCLUDED_LEVEL2_IDS = {"stash", "workbench"}
VOLATILE_TIMESTAMP_KEYS = {"generatedAt", "lastUpdated", "lastupdated"}


def _load_state(data_dir: Path, rules_path: Path) -> dict:
    metadata = load_json(data_dir / "metadata.json", {})
    items = load_json(data_dir / "items.json", [])
    quests = load_json(data_dir / "quests.json", [])
    quest_graph = load_json(data_dir / "quests_graph.json", {})
    rules = load_json(rules_path, {})

    item_count = metadata.get("itemCount")
    if not isinstance(item_count, int):
        item_count = len(items) if isinstance(items, list) else 0

    quest_count = metadata.get("questCount")
    if not isinstance(quest_count, int):
        quest_count = len(quests) if isinstance(quests, list) else 0

    return {
        "metadata": metadata if isinstance(metadata, dict) else {},
        "items": items if isinstance(items, list) else [],
        "quests": quests if isinstance(quests, list) else [],
        "quest_graph": quest_graph if isinstance(quest_graph, dict) else {},
        "rules": rules if isinstance(rules, dict) else {},
        "item_count": item_count,
        "quest_count": quest_count,
    }


def _capture_file_bytes(paths: Iterable[Path]) -> dict[Path, bytes]:
    captured: dict[Path, bytes] = {}
    for path in paths:
        if path.exists():
            captured[path] = path.read_bytes()
        else:
            captured[path] = b""
    return captured


def _normalize_for_semantic_diff(value: object) -> object:
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str) or key in VOLATILE_TIMESTAMP_KEYS:
                continue
            normalized[key] = _normalize_for_semantic_diff(nested_value)
        return normalized
    if isinstance(value, list):
        return [_normalize_for_semantic_diff(entry) for entry in value]
    return value


def _is_ignorable_timestamp_only_json_diff(before: bytes, after: bytes) -> bool:
    if not before or not after:
        return False

    try:
        before_json = orjson.loads(before)
        after_json = orjson.loads(after)
    except (orjson.JSONDecodeError, UnicodeDecodeError):
        return False

    return _normalize_for_semantic_diff(before_json) == _normalize_for_semantic_diff(after_json)


def _diff_changed_files(
    before_bytes: dict[Path, bytes],
    after_bytes: dict[Path, bytes],
    *,
    ignore_timestamp_only_diffs: bool = False,
) -> list[str]:
    changed: list[str] = []
    for path in sorted(before_bytes.keys(), key=lambda p: str(p)):
        before_value = before_bytes.get(path, b"")
        after_value = after_bytes.get(path, b"")
        if before_value == after_value:
            continue

        if ignore_timestamp_only_diffs and _is_ignorable_timestamp_only_json_diff(before_value, after_value):
            continue

        changed.append(path.relative_to(REPO_ROOT).as_posix())
    return changed


def _copy_support_files_for_temp_run(source_data_dir: Path, temp_data_dir: Path) -> None:
    quest_graph_path = source_data_dir / "quests_graph.json"
    if quest_graph_path.exists():
        shutil.copy2(quest_graph_path, temp_data_dir / "quests_graph.json")

    source_static = source_data_dir / "static"
    temp_static = temp_data_dir / "static"
    if source_static.exists():
        shutil.copytree(source_static, temp_static, dirs_exist_ok=True)
    else:
        temp_static.mkdir(parents=True, exist_ok=True)


def _fetch_default_user_context() -> tuple[dict[str, int], list[str]]:
    """Fetch default hideout levels and completed projects from public API."""
    client = ArcTrackerClient()

    # Default hideout levels: assume level 2 for all standard modules
    hideout_levels: dict[str, int] = {}
    public_hideout = client.get_public_hideout()
    # Public API returns { "hideoutModules": { "id": { ... } } }
    modules_dict = (public_hideout or {}).get("hideoutModules")
    if isinstance(modules_dict, dict):
        for module_id, module in modules_dict.items():
            if not module_id or module_id in EXCLUDED_LEVEL2_IDS:
                continue
            max_level = module.get("maxLevel", 0)
            hideout_levels[module_id] = min(2, max_level)

    # Default completed projects: assume all projects are completed for rules
    completed_projects: list[str] = []
    public_projects = client.get_public_projects()
    # Public API returns { "projects": { "id": { ... } } }
    projects_dict = (public_projects or {}).get("projects")
    if isinstance(projects_dict, dict):
        for project_id in projects_dict:
            if project_id:
                completed_projects.append(project_id)

    return hideout_levels, completed_projects


def _update_in_place(data_dir: Path, rules_path: Path) -> dict:
    snapshot_metadata = update_data_snapshot(data_dir)
    hideout_levels, completed_projects = _fetch_default_user_context()

    rules_payload = generate_rules_from_active(
        active_quests=[],
        hideout_levels=hideout_levels,
        completed_projects=completed_projects,
        all_quests_completed=True,
        data_dir=data_dir,
    )
    write_rules(rules_payload, rules_path)

    return {
        "snapshot_metadata": snapshot_metadata,
        "rules_payload": rules_payload,
        "hideout_levels": hideout_levels,
    }


def _update_dry_run(source_data_dir: Path) -> dict:
    with TemporaryDirectory() as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        temp_data_dir = temp_dir / "data"
        temp_rules_path = temp_dir / "items_rules.default.json"

        temp_data_dir.mkdir(parents=True, exist_ok=True)
        _copy_support_files_for_temp_run(source_data_dir, temp_data_dir)

        snapshot_metadata = update_data_snapshot(temp_data_dir)
        hideout_levels, completed_projects = _fetch_default_user_context()

        rules_payload = generate_rules_from_active(
            active_quests=[],
            hideout_levels=hideout_levels,
            completed_projects=completed_projects,
            all_quests_completed=True,
            data_dir=temp_data_dir,
        )
        write_rules(rules_payload, temp_rules_path)

        after_state = _load_state(temp_data_dir, temp_rules_path)

        target_paths = [REPO_ROOT / relative for relative in TARGET_RELATIVE_FILES]
        before_bytes = _capture_file_bytes(target_paths)
        after_bytes = _capture_file_bytes([
            temp_data_dir / "items.json",
            temp_data_dir / "quests.json",
            temp_data_dir / "quests_by_trader.json",
            temp_data_dir / "metadata.json",
            temp_rules_path,
        ])
        mapped_after = {
            target_paths[0]: after_bytes[temp_data_dir / "items.json"],
            target_paths[1]: after_bytes[temp_data_dir / "quests.json"],
            target_paths[2]: after_bytes[temp_data_dir / "quests_by_trader.json"],
            target_paths[3]: after_bytes[temp_data_dir / "metadata.json"],
            target_paths[4]: after_bytes[temp_rules_path],
        }
        changed_files = _diff_changed_files(
            before_bytes,
            mapped_after,
            ignore_timestamp_only_diffs=True,
        )

        return {
            "snapshot_metadata": snapshot_metadata,
            "rules_payload": rules_payload,
            "hideout_levels": hideout_levels,
            "after_state": after_state,
            "changed_files": changed_files,
        }


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def build_report(
    *,
    before_state: dict,
    after_state: dict,
    changed_files: list[str],
    hideout_levels: dict[str, int],
    dry_run: bool,
) -> dict:
    quests = diff_quests(before_state.get("quests", []), after_state.get("quests", []))
    rules = diff_rules(before_state.get("rules", {}), after_state.get("rules", {}))
    quest_graph = graph_gap_report(after_state.get("quests", []), after_state.get("quest_graph", {}))

    before_metadata = before_state.get("metadata", {})
    after_metadata = after_state.get("metadata", {})
    before_last_updated = before_metadata.get("lastUpdated") if isinstance(before_metadata, dict) else "unknown"
    after_last_updated = after_metadata.get("lastUpdated") if isinstance(after_metadata, dict) else "unknown"

    workshop_ids = sorted(hideout_levels.keys())

    return {
        "generatedAt": iso_now(),
        "gitSha": _git_sha(),
        "mode": "dry-run" if dry_run else "write",
        "snapshot": {
            "beforeItemCount": before_state.get("item_count", 0),
            "afterItemCount": after_state.get("item_count", 0),
            "beforeQuestCount": before_state.get("quest_count", 0),
            "afterQuestCount": after_state.get("quest_count", 0),
            "beforeLastUpdated": before_last_updated,
            "afterLastUpdated": after_last_updated,
            "changedFiles": changed_files,
        },
        "quests": quests,
        "rules": rules,
        "questGraph": quest_graph,
        "assumptions": {
            "allQuestsCompleted": True,
            "workshopProfile": "level-2-workshops",
            "workshopIds": workshop_ids,
            "excludedIds": sorted(EXCLUDED_LEVEL2_IDS),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Update progress snapshot and regenerate default rules using all quests completed + level-2 workshops."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Path to progress data directory.",
    )
    parser.add_argument(
        "--rules-path",
        type=Path,
        default=DEFAULT_RULES_PATH,
        help="Path to default rules json file.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=REPO_ROOT / "artifacts" / "update-report.json",
        help="Output path for machine-readable report.",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=REPO_ROOT / "artifacts" / "update-report.md",
        help="Output path for markdown summary report.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Max number of entries to include in markdown samples.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate report against a temporary snapshot without writing tracked files.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    rules_path = args.rules_path.resolve()
    report_json_path = args.report_json.resolve()
    report_md_path = args.report_md.resolve()

    before_state = _load_state(data_dir, rules_path)

    if args.dry_run:
        result = _update_dry_run(data_dir)
        after_state = result["after_state"]
        changed_files = result["changed_files"]
        hideout_levels = result["hideout_levels"]
    else:
        target_paths = [REPO_ROOT / relative for relative in TARGET_RELATIVE_FILES]
        before_bytes = _capture_file_bytes(target_paths)

        result = _update_in_place(data_dir, rules_path)
        after_state = _load_state(data_dir, rules_path)
        after_bytes = _capture_file_bytes(target_paths)
        changed_files = _diff_changed_files(
            before_bytes,
            after_bytes,
            ignore_timestamp_only_diffs=True,
        )
        hideout_levels = result["hideout_levels"]

    report = build_report(
        before_state=before_state,
        after_state=after_state,
        changed_files=changed_files,
        hideout_levels=hideout_levels,
        dry_run=bool(args.dry_run),
    )

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_bytes(orjson.dumps(report, option=orjson.OPT_INDENT_2))

    markdown = build_markdown_summary(report, sample_limit=max(1, args.sample_limit))
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.write_text(markdown, encoding="utf-8")

    print(
        "Update report generated: "
        f"items {report['snapshot']['beforeItemCount']} -> {report['snapshot']['afterItemCount']}, "
        f"quests {report['snapshot']['beforeQuestCount']} -> {report['snapshot']['afterQuestCount']}, "
        f"changed files {len(report['snapshot']['changedFiles'])}."
    )
    print(f"Report JSON: {report_json_path}")
    print(f"Report Markdown: {report_md_path}")

    graph_missing = report.get("questGraph", {}).get("questsMissingFromGraphCount", 0)
    if isinstance(graph_missing, int) and graph_missing > 0:
        print(f"Warning: {graph_missing} quests are missing from quests_graph.json; workflow continues by design.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
