"""Data source for fetching inventory data from ArcTracker API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from ..config import ApiSettings, ProgressSettings, load_api_settings, load_progress_settings, save_progress_settings
from ..core.item_actions import ActionMap, ItemActionResult, normalize_item_name
from ..interaction.inventory_grid import Cell
from .client import ArcTrackerClient

if TYPE_CHECKING:
    from ..scanner.types import ScanStats

_log = logging.getLogger(__name__)


type DataSourceType = Literal["api", "ocr"]


@dataclass(slots=True)
class APIDataSource:
    """Data source using ArcTracker API."""

    client: ArcTrackerClient
    actions: ActionMap
    dry_run: bool = False

    def fetch_stash(self) -> list[ItemActionResult]:
        """Fetch stash from API and convert to scan results."""
        stash_data = self.client.get_all_stash_items()

        if stash_data.api_error:
            _log.warning("api: Failed to fetch stash: %s", stash_data.api_error)
            return []

        results: list[ItemActionResult] = []
        for idx, item in enumerate(stash_data.items):
            # Normalize the item name for decision lookup
            normalized_name = normalize_item_name(item.name)

            # Look up decision in actions map
            decision_list = self.actions.get(normalized_name)
            decision = decision_list[0] if decision_list else None

            # Create a synthetic cell for the result
            slot_idx = item.slot if item.slot is not None else idx
            page = slot_idx // 20  # 20 items per page (4x5 grid)
            cell_index = slot_idx % 20
            row = cell_index // 4
            col = cell_index % 4
            cell = Cell(
                index=cell_index,
                row=row,
                col=col,
                x=0,
                y=0,
                width=0,
                height=0,
                safe_bounds=(0, 0, 0, 0),
            )

            # Determine action taken
            if self.dry_run:
                action_taken = "dry-run"
            elif decision == "KEEP":
                action_taken = "skipped"
            elif decision == "SELL":
                action_taken = "sell"
            elif decision == "RECYCLE":
                action_taken = "recycle"
            else:
                action_taken = "no-action"

            results.append(
                ItemActionResult(
                    page=page,
                    cell=cell,
                    item_name=item.name,
                    decision=decision,
                    action_taken=action_taken,
                    raw_item_text=item.name,
                    note=f"Qty: {item.quantity}" if item.quantity > 1 else None,
                )
            )

        _log.info("api: Fetched %d items from stash", len(results))
        return results

    def get_stats(self) -> ScanStats:
        """Get scan stats for API fetch."""
        from ..scanner.types import ScanStats

        stash_data = self.client.get_all_stash_items()

        return ScanStats(
            items_in_stash=stash_data.used_slots if not stash_data.api_error else None,
            stash_count_text=str(stash_data.used_slots) if not stash_data.api_error else "api-error",
            pages_planned=1,
            pages_scanned=1,
            processing_seconds=0.0,
        )


def fetch_stash_as_scan_results(
    actions: ActionMap,
    api_settings: ApiSettings | None = None,
    dry_run: bool = False,
) -> tuple[list[ItemActionResult], ScanStats]:
    """Fetch stash from API and convert to scan results format.

    Args:
        actions: Action map for item decisions.
        api_settings: Optional API settings. If None, loads from config.
        dry_run: Whether this is a dry run.

    Returns:
        Tuple of (results, stats).
    """
    if api_settings is None:
        api_settings = load_api_settings()

    client = ArcTrackerClient(
        app_key=api_settings.app_key or None,
        user_key=api_settings.user_key or None,
        base_url=api_settings.base_url,
    )

    source = APIDataSource(
        client=client,
        actions=actions,
        dry_run=dry_run,
    )

    results = source.fetch_stash()
    stats = source.get_stats()

    return results, stats


def sync_hideout_to_progress(api_settings: ApiSettings | None = None) -> ProgressSettings:
    """Sync hideout levels from API to progress settings."""
    if api_settings is None:
        api_settings = load_api_settings()

    client = ArcTrackerClient(
        app_key=api_settings.app_key or None,
        user_key=api_settings.user_key or None,
        base_url=api_settings.base_url,
    )

    if not client.is_configured():
        _log.warning("api: Cannot sync hideout - API not configured")
        return load_progress_settings()

    modules = client.get_user_hideout()
    if not modules:
        _log.warning("api: No hideout data returned from API")
        return load_progress_settings()

    progress = load_progress_settings()
    hideout_levels = dict(progress.hideout_levels)

    for module in modules:
        hideout_levels[module.module_id] = module.current_level

    updated = ProgressSettings(
        all_quests_completed=progress.all_quests_completed,
        active_quests=list(progress.active_quests),
        completed_quests=list(progress.completed_quests),
        hideout_levels=hideout_levels,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )

    save_progress_settings(updated)
    _log.info("api: Synced %d hideout modules from API", len(modules))

    return updated


def sync_projects_to_progress(api_settings: ApiSettings | None = None) -> ProgressSettings:
    """Sync project progress from API to progress settings."""
    if api_settings is None:
        api_settings = load_api_settings()

    client = ArcTrackerClient(
        app_key=api_settings.app_key or None,
        user_key=api_settings.user_key or None,
        base_url=api_settings.base_url,
    )

    if not client.is_configured():
        _log.warning("api: Cannot sync projects - API not configured")
        return load_progress_settings()

    projects = client.get_user_projects()
    if not projects:
        _log.warning("api: No project data returned from API")
        return load_progress_settings()

    progress = load_progress_settings()

    updated = ProgressSettings(
        all_quests_completed=progress.all_quests_completed,
        active_quests=list(progress.active_quests),
        completed_quests=list(progress.completed_quests),
        hideout_levels=dict(progress.hideout_levels),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )

    save_progress_settings(updated)
    _log.info("api: Synced %d projects from API", len(projects))

    return updated


def get_data_source(
    source_type: DataSourceType,
    actions: ActionMap,
    api_settings: ApiSettings | None = None,
    dry_run: bool = False,
) -> APIDataSource | None:
    """Get a data source by type."""
    if source_type != "api":
        return None

    if api_settings is None:
        api_settings = load_api_settings()

    client = ArcTrackerClient(
        app_key=api_settings.app_key or None,
        user_key=api_settings.user_key or None,
        base_url=api_settings.base_url,
    )

    if not client.is_configured():
        _log.warning("api: Cannot use API data source - not configured")
        return None

    return APIDataSource(
        client=client,
        actions=actions,
        dry_run=dry_run,
    )
