from __future__ import annotations

import math
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .progress import RichScanProgress, ScanProgress
from .rich_support import Console
from .scan_loop import ScanContext, TimingConfig, detect_grid, scan_pages
from .types import ScanStats
from ..config import ScanSettings
from ..core.item_actions import (
    ActionMap,
    ITEM_RULES_PATH,
    ItemActionResult,
    load_item_actions,
)
from ..interaction.inventory_grid import (
    Grid,
    grid_center_point,
    inventory_roi_rect,
    safe_mouse_point,
)
from ..interaction.keybinds import DEFAULT_STOP_KEY, normalize_stop_key
from ..interaction.ui_windows import (
    WindowSnapshot,
    WINDOW_TIMEOUT,
    abort_if_escape_pressed,
    capture_region,
    move_absolute,
    pause_action,
    wait_for_target_window,
    window_display_info,
    window_monitor_rect,
    window_rect,
)
from ..ocr.inventory_vision import inventory_count_rect, ocr_inventory_count
from ..ocr.tesseract import initialize_ocr

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Keep runtime scanner defaults anchored to persisted scan settings.
_DEFAULT_SCAN_SETTINGS = ScanSettings()
INFOBOX_RETRIES = _DEFAULT_SCAN_SETTINGS.infobox_retries
INFOBOX_RETRY_INTERVAL_MS = _DEFAULT_SCAN_SETTINGS.infobox_retry_interval_ms
OCR_UNREADABLE_RETRIES = _DEFAULT_SCAN_SETTINGS.ocr_unreadable_retries
OCR_RETRY_INTERVAL_MS = _DEFAULT_SCAN_SETTINGS.ocr_retry_interval_ms
INPUT_ACTION_DELAY_MS = _DEFAULT_SCAN_SETTINGS.input_action_delay_ms
CELL_INFOBOX_LEFT_RIGHT_CLICK_GAP_MS = (
    _DEFAULT_SCAN_SETTINGS.cell_infobox_left_right_click_gap_ms
)
ITEM_INFOBOX_SETTLE_DELAY_MS = _DEFAULT_SCAN_SETTINGS.item_infobox_settle_delay_ms
POST_SELL_RECYCLE_DELAY_MS = _DEFAULT_SCAN_SETTINGS.post_sell_recycle_delay_ms


def _validate_scan_args(
    *,
    infobox_retries: int,
    infobox_retry_interval_ms: int,
    ocr_unreadable_retries: int,
    ocr_retry_interval_ms: int,
    input_action_delay_ms: int,
    cell_infobox_left_right_click_gap_ms: int,
    item_infobox_settle_delay_ms: int,
    post_sell_recycle_delay_ms: int,
    pages: Optional[int],
) -> None:
    if infobox_retries < 1:
        raise ValueError("infobox_retries must be >= 1")
    if infobox_retry_interval_ms < 0:
        raise ValueError("infobox_retry_interval_ms must be >= 0")
    if ocr_unreadable_retries < 0:
        raise ValueError("ocr_unreadable_retries must be >= 0")
    if ocr_retry_interval_ms < 0:
        raise ValueError("ocr_retry_interval_ms must be >= 0")
    if input_action_delay_ms < 0:
        raise ValueError("input_action_delay_ms must be >= 0")
    if cell_infobox_left_right_click_gap_ms < 0:
        raise ValueError("cell_infobox_left_right_click_gap_ms must be >= 0")
    if item_infobox_settle_delay_ms < 0:
        raise ValueError("item_infobox_settle_delay_ms must be >= 0")
    if post_sell_recycle_delay_ms < 0:
        raise ValueError("post_sell_recycle_delay_ms must be >= 0")
    if pages is not None and pages < 1:
        raise ValueError("pages must be >= 1")


def _build_timing_config(
    *,
    input_action_delay_ms: int,
    cell_infobox_left_right_click_gap_ms: int,
    item_infobox_settle_delay_ms: int,
    infobox_retry_interval_ms: int,
    post_sell_recycle_delay_ms: int,
    ocr_retry_interval_ms: int,
) -> TimingConfig:
    return TimingConfig(
        input_action_delay=input_action_delay_ms / 1000.0,
        cell_infobox_left_right_click_gap=cell_infobox_left_right_click_gap_ms / 1000.0,
        item_infobox_settle_delay=item_infobox_settle_delay_ms / 1000.0,
        infobox_retry_interval=infobox_retry_interval_ms / 1000.0,
        post_sell_recycle_delay=post_sell_recycle_delay_ms / 1000.0,
        ocr_retry_interval=ocr_retry_interval_ms / 1000.0,
    )


def _build_progress_impl(
    show_progress: bool,
    progress: Optional[ScanProgress],
) -> Optional[ScanProgress]:
    if progress is not None:
        return progress
    if not show_progress or Console is None:
        return None
    try:
        return RichScanProgress()
    except Exception:
        return None


def _collect_window_bounds_warnings(
    *,
    mon_left: int,
    mon_top: int,
    mon_right: int,
    mon_bottom: int,
    win_left: int,
    win_top: int,
    win_right: int,
    win_bottom: int,
    work_area: Tuple[int, int, int, int],
) -> List[Tuple[str, str]]:
    work_left, work_top, work_right, work_bottom = work_area
    win_is_full_monitor = (
        win_left == mon_left
        and win_top == mon_top
        and win_right == mon_right
        and win_bottom == mon_bottom
    )

    startup_events: List[Tuple[str, str]] = []
    if (
        win_left < mon_left
        or win_top < mon_top
        or win_right > mon_right
        or win_bottom > mon_bottom
    ):
        startup_events.append(
            (
                "Target window extends beyond its display bounds; ensure it is fully visible.",
                "yellow",
            )
        )
    elif not win_is_full_monitor and (
        win_left < work_left
        or win_top < work_top
        or win_right > work_right
        or win_bottom > work_bottom
    ):
        startup_events.append(
            (
                "Target window overlaps the OS taskbar/dock area; ensure no UI is obscured.",
                "yellow",
            )
        )

    return startup_events


def _detect_inventory_count(
    *,
    win_left: int,
    win_top: int,
    win_width: int,
    win_height: int,
    safe_point_abs: Tuple[int, int],
    stop_key: str,
    action_delay: float,
    startup_events: List[Tuple[str, str]],
) -> Tuple[Optional[int], str]:
    """
    Capture the stash count label while the cursor is in a safe spot.
    """
    try:
        move_absolute(safe_point_abs[0], safe_point_abs[1], stop_key=stop_key)
        pause_action(action_delay, stop_key=stop_key)
        count_roi_rel = inventory_count_rect(win_width, win_height)
        count_left = win_left + count_roi_rel[0]
        count_top = win_top + count_roi_rel[1]
        count_bgr = capture_region(
            (count_left, count_top, count_roi_rel[2], count_roi_rel[3])
        )
        return ocr_inventory_count(count_bgr)
    except Exception as exc:
        startup_events.append((f"Failed to read stash count: {exc}", "yellow"))
        return None, ""


def scan_inventory(
    window_timeout: float = WINDOW_TIMEOUT,
    infobox_retries: int = INFOBOX_RETRIES,
    infobox_retry_interval_ms: int = INFOBOX_RETRY_INTERVAL_MS,
    ocr_unreadable_retries: int = OCR_UNREADABLE_RETRIES,
    ocr_retry_interval_ms: int = OCR_RETRY_INTERVAL_MS,
    stop_key: str = DEFAULT_STOP_KEY,
    input_action_delay_ms: int = INPUT_ACTION_DELAY_MS,
    cell_infobox_left_right_click_gap_ms: int = CELL_INFOBOX_LEFT_RIGHT_CLICK_GAP_MS,
    item_infobox_settle_delay_ms: int = ITEM_INFOBOX_SETTLE_DELAY_MS,
    post_sell_recycle_delay_ms: int = POST_SELL_RECYCLE_DELAY_MS,
    show_progress: bool = True,
    pages: Optional[int] = None,
    apply_actions: bool = True,
    actions_path: Path = ITEM_RULES_PATH,
    actions_override: Optional[ActionMap] = None,
    profile_timing: bool = False,
    progress: Optional[ScanProgress] = None,
    window_snapshot: Optional[WindowSnapshot] = None,
) -> Tuple[List[ItemActionResult], ScanStats]:
    """
    Walk each 4x5 grid (top-to-bottom, left-to-right), OCR each cell's item
    title, and apply the configured keep/recycle/sell decision when possible.
    Decisions come from the default rules file unless a custom rules file exists
    or an override map is provided.
    Cells are detected via contours inside a normalized ROI, and scrolling uses
    a calibrated repeating click pattern to handle carousel offset. If `pages`
    is not provided, the script will
    OCR the always-visible stash count label to automatically determine how
    many 4x5 grids to scan.
    """
    _validate_scan_args(
        infobox_retries=infobox_retries,
        infobox_retry_interval_ms=infobox_retry_interval_ms,
        ocr_unreadable_retries=ocr_unreadable_retries,
        ocr_retry_interval_ms=ocr_retry_interval_ms,
        input_action_delay_ms=input_action_delay_ms,
        cell_infobox_left_right_click_gap_ms=cell_infobox_left_right_click_gap_ms,
        item_infobox_settle_delay_ms=item_infobox_settle_delay_ms,
        post_sell_recycle_delay_ms=post_sell_recycle_delay_ms,
        pages=pages,
    )

    stop_key = normalize_stop_key(stop_key)
    timing = _build_timing_config(
        input_action_delay_ms=input_action_delay_ms,
        cell_infobox_left_right_click_gap_ms=cell_infobox_left_right_click_gap_ms,
        item_infobox_settle_delay_ms=item_infobox_settle_delay_ms,
        infobox_retry_interval_ms=infobox_retry_interval_ms,
        post_sell_recycle_delay_ms=post_sell_recycle_delay_ms,
        ocr_retry_interval_ms=ocr_retry_interval_ms,
    )

    scan_start = time.perf_counter()

    _ocr_info = initialize_ocr()

    progress_impl = _build_progress_impl(show_progress, progress)
    if progress_impl is not None:
        progress_impl.start()
        if window_snapshot is None:
            progress_impl.set_phase("Waiting for Arc Raiders window…")

    try:
        window = None
        if window_snapshot is None:
            if progress_impl is not None:
                window = wait_for_target_window(
                    timeout=window_timeout, stop_key=stop_key
                )
            else:
                print("waiting for Arc Raiders to be active window...", flush=True)
                window = wait_for_target_window(
                    timeout=window_timeout, stop_key=stop_key
                )

            _display_name, _display_size, work_area = window_display_info(window)
            mon_left, mon_top, mon_right, mon_bottom = window_monitor_rect(window)

            win_left, win_top, win_width, win_height = window_rect(window)
        else:
            work_area = window_snapshot.work_area
            mon_left = window_snapshot.mon_left
            mon_top = window_snapshot.mon_top
            mon_right = window_snapshot.mon_right
            mon_bottom = window_snapshot.mon_bottom
            win_left = window_snapshot.win_left
            win_top = window_snapshot.win_top
            win_width = window_snapshot.win_width
            win_height = window_snapshot.win_height
        win_right = win_left + win_width
        win_bottom = win_top + win_height

        startup_events = _collect_window_bounds_warnings(
            mon_left=mon_left,
            mon_top=mon_top,
            mon_right=mon_right,
            mon_bottom=mon_bottom,
            win_left=win_left,
            win_top=win_top,
            win_right=win_right,
            win_bottom=win_bottom,
            work_area=work_area,
        )

        actions: ActionMap = (
            actions_override
            if actions_override is not None
            else load_item_actions(actions_path)
        )

        grid_roi = inventory_roi_rect(win_width, win_height)
        safe_point = safe_mouse_point(win_width, win_height)
        safe_point_abs = (win_left + safe_point[0], win_top + safe_point[1])
        grid_center = grid_center_point(win_width, win_height)
        grid_center_abs = (win_left + grid_center[0], win_top + grid_center[1])
        cells_per_page = Grid.COLS * Grid.ROWS

        stash_items, stash_count_text = _detect_inventory_count(
            win_left=win_left,
            win_top=win_top,
            win_width=win_width,
            win_height=win_height,
            safe_point_abs=safe_point_abs,
            stop_key=stop_key,
            action_delay=timing.input_action_delay,
            startup_events=startup_events,
        )
        auto_pages = (
            math.ceil(stash_items / cells_per_page) if stash_items is not None else None
        )
        pages_to_scan = pages if pages is not None else auto_pages or 1
        pages_to_scan = max(1, pages_to_scan)
        pages_source = "cli" if pages is not None else "auto"
        items_label = stash_items if stash_items is not None else "?"

        context = ScanContext(
            window=window,
            stop_key=stop_key,
            win_left=win_left,
            win_top=win_top,
            win_width=win_width,
            win_height=win_height,
            grid_roi=grid_roi,
            safe_point_abs=safe_point_abs,
            grid_center_abs=grid_center_abs,
            cells_per_page=cells_per_page,
            actions=actions,
            apply_actions=apply_actions,
            timing=timing,
        )

        grid = detect_grid(context, progress_impl, startup_events)
        cells = list(grid)
        total_cells = cells_per_page * pages_to_scan
        items_total = stash_items if stash_items is not None else total_cells

        abort_if_escape_pressed(stop_key)

        if progress_impl is not None:
            progress_impl.set_mode("Dry run" if not apply_actions else "Scan")
            if stash_items is None and stash_count_text:
                progress_impl.set_stash_label(f"? items (OCR '{stash_count_text}')")
            else:
                progress_impl.set_stash_label(f"{items_label} items")
            progress_impl.set_pages_label(f"{pages_to_scan} ({pages_source})")
            progress_impl.set_total(items_total)
            progress_impl.set_phase("Scanning…")
            progress_impl.start_timer()
            for message, style in startup_events:
                progress_impl.add_event(message, style=style)
            startup_events.clear()
        else:
            for message, _style in startup_events:
                print(f"[warning] {message}", flush=True)
            startup_events.clear()

        run_state = scan_pages(
            context=context,
            initial_cells=cells,
            pages_to_scan=pages_to_scan,
            infobox_retries=infobox_retries,
            ocr_unreadable_retries=ocr_unreadable_retries,
            profile_timing=profile_timing,
            progress_impl=progress_impl,
            startup_events=startup_events,
            items_total=items_total,
        )

        processing_seconds = time.perf_counter() - scan_start
        stats = ScanStats(
            items_in_stash=stash_items,
            stash_count_text=stash_count_text,
            pages_planned=pages_to_scan,
            pages_scanned=run_state.pages_scanned,
            processing_seconds=processing_seconds,
        )

        return run_state.results, stats
    finally:
        if progress_impl is not None:
            progress_impl.stop()
