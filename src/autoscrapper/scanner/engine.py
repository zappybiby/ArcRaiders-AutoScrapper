from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from .actions import MENU_APPEAR_DELAY, _perform_recycle, _perform_sell
from .outcomes import _describe_action
from .progress import RichScanProgress, ScanProgress
from .rich_support import Console
from .types import ScanStats
from ..core.item_actions import (
    ActionMap,
    Decision,
    ITEM_RULES_PATH,
    ItemActionResult,
    choose_decision,
    load_item_actions,
)
from ..interaction.inventory_grid import (
    Cell,
    Grid,
    grid_center_point,
    inventory_roi_rect,
    safe_mouse_point,
)
from ..interaction.ui_windows import (
    ACTION_DELAY,
    SCROLL_ALT_CLICKS_PER_PAGE,
    SCROLL_CLICKS_PER_PAGE,
    SELL_RECYCLE_POST_DELAY,
    WINDOW_TIMEOUT,
    abort_if_escape_pressed,
    capture_region,
    move_absolute,
    open_cell_menu,
    pause_action,
    scroll_to_next_grid_at,
    sleep_with_abort,
    wait_for_target_window,
    window_display_info,
    window_monitor_rect,
    window_rect,
)
from ..interaction.keybinds import DEFAULT_STOP_KEY, normalize_stop_key
from ..ocr.inventory_vision import (
    InfoboxOcrResult,
    find_infobox,
    inventory_count_rect,
    is_slot_empty,
    ocr_infobox,
    ocr_inventory_count,
)
from ..ocr.tesseract import initialize_ocr

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INFOBOX_RETRY_DELAY = 0.10
INFOBOX_RETRIES = 3


@dataclass(frozen=True)
class _TimingConfig:
    action_delay: float
    menu_appear_delay: float
    infobox_retry_delay: float
    post_action_delay: float
    ocr_unreadable_retry_delay: float


@dataclass(frozen=True)
class _ScanContext:
    window: Any
    stop_key: str
    win_left: int
    win_top: int
    win_width: int
    win_height: int
    grid_roi: Tuple[int, int, int, int]
    safe_point_abs: Tuple[int, int]
    grid_center_abs: Tuple[int, int]
    cells_per_page: int
    actions: ActionMap
    apply_actions: bool
    timing: _TimingConfig


@dataclass(frozen=True)
class _InfoboxCaptureResult:
    infobox_rect: Optional[Tuple[int, int, int, int]]
    window_bgr: Optional[Any]
    capture_time: float
    find_time: float
    capture_attempts: int
    found_on_attempt: int


@dataclass(frozen=True)
class _InfoboxReadResult:
    infobox_ocr: Optional[InfoboxOcrResult]
    item_name: str
    raw_item_text: str
    sell_bbox_rel: Optional[Tuple[int, int, int, int]]
    recycle_bbox_rel: Optional[Tuple[int, int, int, int]]
    preprocess_time: float
    ocr_time: float


@dataclass(frozen=True)
class _CellScanResult:
    result: ItemActionResult
    action_label: str
    item_label: str
    action_taken: str


@dataclass
class _ScanRunState:
    results: List[ItemActionResult] = field(default_factory=list)
    pages_scanned: int = 0
    stop_at_global_idx: Optional[int] = None


def _scroll_clicks_sequence(start_clicks: int, alt_clicks: int) -> Iterable[int]:
    """
    Yield alternating scroll counts: start_clicks, alt_clicks, repeat.
    """
    base = abs(start_clicks)
    alt = abs(alt_clicks)
    use_alt = False
    while True:
        yield alt if use_alt else base
        use_alt = not use_alt


def _validate_scan_args(
    *,
    infobox_retries: int,
    infobox_retry_delay_ms: int,
    ocr_unreadable_retries: int,
    ocr_unreadable_retry_delay_ms: int,
    action_delay_ms: int,
    menu_appear_delay_ms: int,
    sell_recycle_post_delay_ms: int,
    pages: Optional[int],
    scroll_clicks_per_page: int,
    scroll_clicks_alt_per_page: int,
) -> None:
    if infobox_retries < 1:
        raise ValueError("infobox_retries must be >= 1")
    if infobox_retry_delay_ms < 0:
        raise ValueError("infobox_retry_delay_ms must be >= 0")
    if ocr_unreadable_retries < 0:
        raise ValueError("ocr_unreadable_retries must be >= 0")
    if ocr_unreadable_retry_delay_ms < 0:
        raise ValueError("ocr_unreadable_retry_delay_ms must be >= 0")
    if action_delay_ms < 0:
        raise ValueError("action_delay_ms must be >= 0")
    if menu_appear_delay_ms < 0:
        raise ValueError("menu_appear_delay_ms must be >= 0")
    if sell_recycle_post_delay_ms < 0:
        raise ValueError("sell_recycle_post_delay_ms must be >= 0")
    if pages is not None and pages < 1:
        raise ValueError("pages must be >= 1")
    if scroll_clicks_per_page < 0:
        raise ValueError("scroll_clicks_per_page must be >= 0")
    if scroll_clicks_alt_per_page < 0:
        raise ValueError("scroll_clicks_alt_per_page must be >= 0")


def _build_timing_config(
    *,
    action_delay_ms: int,
    menu_appear_delay_ms: int,
    infobox_retry_delay_ms: int,
    sell_recycle_post_delay_ms: int,
    ocr_unreadable_retry_delay_ms: int,
) -> _TimingConfig:
    return _TimingConfig(
        action_delay=action_delay_ms / 1000.0,
        menu_appear_delay=menu_appear_delay_ms / 1000.0,
        infobox_retry_delay=infobox_retry_delay_ms / 1000.0,
        post_action_delay=sell_recycle_post_delay_ms / 1000.0,
        ocr_unreadable_retry_delay=ocr_unreadable_retry_delay_ms / 1000.0,
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


def _queue_event(
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
    message: str,
    *,
    style: str = "dim",
) -> None:
    if progress_impl is not None:
        progress_impl.add_event(message, style=style)
    else:
        startup_events.append((message, style))


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


def _detect_grid(
    context: _ScanContext,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
) -> Grid:
    """
    Move the cursor out of the grid, capture the ROI, and detect cells.
    """
    move_absolute(
        context.safe_point_abs[0],
        context.safe_point_abs[1],
        stop_key=context.stop_key,
    )
    pause_action(context.timing.action_delay, stop_key=context.stop_key)
    roi_left = context.win_left + context.grid_roi[0]
    roi_top = context.win_top + context.grid_roi[1]
    inv_bgr = capture_region(
        (roi_left, roi_top, context.grid_roi[2], context.grid_roi[3])
    )
    grid = Grid.detect(inv_bgr, context.grid_roi, context.win_width, context.win_height)
    expected_cells = Grid.COLS * Grid.ROWS
    if len(grid) < expected_cells:
        _queue_event(
            progress_impl,
            startup_events,
            f"Detected {len(grid)} cells inside the grid ROI (expected {expected_cells}); "
            "grid may be partially obscured or ROI misaligned.",
            style="yellow",
        )
    return grid


def _should_stop_at_index(
    *,
    global_idx: int,
    stop_at_global_idx: Optional[int],
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
) -> bool:
    if stop_at_global_idx is None or global_idx < stop_at_global_idx:
        return False

    _queue_event(
        progress_impl,
        startup_events,
        f"Reached empty slot idx={stop_at_global_idx:03d}; stopping scan.",
        style="yellow",
    )
    if progress_impl is not None:
        progress_impl.set_phase("Stopping…")
    return True


def _capture_infobox_with_retries(
    context: _ScanContext,
    *,
    infobox_retries: int,
) -> _InfoboxCaptureResult:
    infobox_rect: Optional[Tuple[int, int, int, int]] = None
    window_bgr = None
    capture_time = 0.0
    find_time = 0.0
    capture_attempts = 0
    found_on_attempt = 0

    for attempt in range(1, infobox_retries + 1):
        capture_attempts += 1
        abort_if_escape_pressed(context.stop_key)

        capture_start = time.perf_counter()
        window_bgr = capture_region(
            (context.win_left, context.win_top, context.win_width, context.win_height)
        )
        capture_time += time.perf_counter() - capture_start

        find_start = time.perf_counter()
        infobox_rect = find_infobox(window_bgr)
        find_time += time.perf_counter() - find_start

        if infobox_rect:
            found_on_attempt = attempt
            break

        sleep_with_abort(context.timing.infobox_retry_delay, stop_key=context.stop_key)
        pause_action(context.timing.action_delay, stop_key=context.stop_key)

    return _InfoboxCaptureResult(
        infobox_rect=infobox_rect,
        window_bgr=window_bgr,
        capture_time=capture_time,
        find_time=find_time,
        capture_attempts=capture_attempts,
        found_on_attempt=found_on_attempt,
    )


def _ocr_infobox_with_retries(
    context: _ScanContext,
    *,
    capture_result: _InfoboxCaptureResult,
    ocr_unreadable_retries: int,
) -> _InfoboxReadResult:
    infobox_rect = capture_result.infobox_rect
    window_bgr = capture_result.window_bgr

    infobox_ocr: Optional[InfoboxOcrResult] = None
    item_name = ""
    raw_item_text = ""
    sell_bbox_rel: Optional[Tuple[int, int, int, int]] = None
    recycle_bbox_rel: Optional[Tuple[int, int, int, int]] = None
    preprocess_time = 0.0
    ocr_time = 0.0

    if infobox_rect is None or window_bgr is None:
        return _InfoboxReadResult(
            infobox_ocr=infobox_ocr,
            item_name=item_name,
            raw_item_text=raw_item_text,
            sell_bbox_rel=sell_bbox_rel,
            recycle_bbox_rel=recycle_bbox_rel,
            preprocess_time=preprocess_time,
            ocr_time=ocr_time,
        )

    pause_action(context.timing.action_delay, stop_key=context.stop_key)
    x, y, w, h = infobox_rect

    for ocr_attempt in range(ocr_unreadable_retries + 1):
        if ocr_attempt > 0:
            sleep_with_abort(
                context.timing.ocr_unreadable_retry_delay,
                stop_key=context.stop_key,
            )
            try:
                infobox_bgr = capture_region(
                    (context.win_left + x, context.win_top + y, w, h)
                )
            except Exception:
                window_bgr = capture_region(
                    (
                        context.win_left,
                        context.win_top,
                        context.win_width,
                        context.win_height,
                    )
                )
                infobox_bgr = window_bgr[y : y + h, x : x + w]
        else:
            infobox_bgr = window_bgr[y : y + h, x : x + w]

        infobox_ocr = ocr_infobox(infobox_bgr)
        preprocess_time += infobox_ocr.preprocess_time
        ocr_time += infobox_ocr.ocr_time
        item_name = infobox_ocr.item_name
        raw_item_text = infobox_ocr.raw_item_text
        sell_bbox_rel = infobox_ocr.sell_bbox
        recycle_bbox_rel = infobox_ocr.recycle_bbox
        if item_name:
            break

    return _InfoboxReadResult(
        infobox_ocr=infobox_ocr,
        item_name=item_name,
        raw_item_text=raw_item_text,
        sell_bbox_rel=sell_bbox_rel,
        recycle_bbox_rel=recycle_bbox_rel,
        preprocess_time=preprocess_time,
        ocr_time=ocr_time,
    )


def _apply_destructive_decision(
    *,
    decision: Decision,
    infobox_rect: Optional[Tuple[int, int, int, int]],
    infobox_ocr: Optional[InfoboxOcrResult],
    action_bbox_rel: Optional[Tuple[int, int, int, int]],
    context: _ScanContext,
) -> str:
    if infobox_rect is None or infobox_ocr is None:
        return "SKIP_NO_INFOBOX"
    if action_bbox_rel is None:
        return "SKIP_NO_ACTION_BBOX"
    if not context.apply_actions:
        return f"DRY_RUN_{decision}"

    if decision == "SELL":
        _perform_sell(
            infobox_rect,
            action_bbox_rel,
            context.win_left,
            context.win_top,
            context.win_width,
            context.win_height,
            stop_key=context.stop_key,
            action_delay=context.timing.action_delay,
            menu_appear_delay=context.timing.menu_appear_delay,
            post_action_delay=context.timing.post_action_delay,
        )
        return "SELL"

    _perform_recycle(
        infobox_rect,
        action_bbox_rel,
        context.win_left,
        context.win_top,
        context.win_width,
        context.win_height,
        stop_key=context.stop_key,
        action_delay=context.timing.action_delay,
        menu_appear_delay=context.timing.menu_appear_delay,
        post_action_delay=context.timing.post_action_delay,
    )
    return "RECYCLE"


def _resolve_action_taken(
    *,
    decision: Optional[Decision],
    item_name: str,
    actions: ActionMap,
    infobox_rect: Optional[Tuple[int, int, int, int]],
    infobox_ocr: Optional[InfoboxOcrResult],
    sell_bbox_rel: Optional[Tuple[int, int, int, int]],
    recycle_bbox_rel: Optional[Tuple[int, int, int, int]],
    context: _ScanContext,
) -> str:
    if decision is None:
        if not item_name:
            if infobox_rect is None:
                return "UNREADABLE_NO_INFOBOX"
            if infobox_ocr is None:
                return "UNREADABLE_NO_OCR"
            if infobox_ocr.ocr_failed:
                return "UNREADABLE_OCR_FAILED"
            return "UNREADABLE_TITLE"
        if not actions:
            return "SKIP_NO_ACTION_MAP"
        return "SKIP_UNLISTED"

    if decision == "KEEP":
        return "KEEP"
    if decision == "SELL":
        return _apply_destructive_decision(
            decision=decision,
            infobox_rect=infobox_rect,
            infobox_ocr=infobox_ocr,
            action_bbox_rel=sell_bbox_rel,
            context=context,
        )
    if decision == "RECYCLE":
        return _apply_destructive_decision(
            decision=decision,
            infobox_rect=infobox_rect,
            infobox_ocr=infobox_ocr,
            action_bbox_rel=recycle_bbox_rel,
            context=context,
        )
    return "SCAN_ONLY"


def _process_cell(
    *,
    page: int,
    cell: Cell,
    context: _ScanContext,
    infobox_retries: int,
    ocr_unreadable_retries: int,
    profile_timing: bool,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
) -> _CellScanResult:
    global_idx = page * context.cells_per_page + cell.index
    cell_start = time.perf_counter()

    abort_if_escape_pressed(context.stop_key)
    if hasattr(context.window, "isAlive") and not context.window.isAlive:  # type: ignore[attr-defined]
        raise RuntimeError("Target window closed during scan")

    sleep_with_abort(context.timing.menu_appear_delay, stop_key=context.stop_key)
    pause_action(context.timing.action_delay, stop_key=context.stop_key)

    capture_result = _capture_infobox_with_retries(
        context,
        infobox_retries=infobox_retries,
    )
    ocr_result = _ocr_infobox_with_retries(
        context,
        capture_result=capture_result,
        ocr_unreadable_retries=ocr_unreadable_retries,
    )

    decision: Optional[Decision] = None
    decision_note: Optional[str] = None
    if context.actions and ocr_result.item_name:
        decision, decision_note = choose_decision(ocr_result.item_name, context.actions)

    action_taken = _resolve_action_taken(
        decision=decision,
        item_name=ocr_result.item_name,
        actions=context.actions,
        infobox_rect=capture_result.infobox_rect,
        infobox_ocr=ocr_result.infobox_ocr,
        sell_bbox_rel=ocr_result.sell_bbox_rel,
        recycle_bbox_rel=ocr_result.recycle_bbox_rel,
        context=context,
    )

    action_label, _details = _describe_action(action_taken)
    item_label = (
        (ocr_result.item_name or ocr_result.raw_item_text or "<unreadable>")
        .replace("\n", " ")
        .strip()
    )

    result = ItemActionResult(
        page=page,
        cell=cell,
        item_name=ocr_result.item_name,
        decision=decision,
        action_taken=action_taken,
        raw_item_text=ocr_result.raw_item_text or None,
        note=decision_note,
    )

    if profile_timing:
        total_time = time.perf_counter() - cell_start
        _queue_event(
            progress_impl,
            startup_events,
            f"Perf idx={global_idx:03d} • tries={capture_result.capture_attempts} • "
            f"found@{capture_result.found_on_attempt} • "
            f"infobox={'y' if capture_result.infobox_rect else 'n'}\n"
            f"  cap {capture_result.capture_time:.3f}s • "
            f"find {capture_result.find_time:.3f}s • "
            f"pre {ocr_result.preprocess_time:.3f}s • "
            f"ocr {ocr_result.ocr_time:.3f}s • total {total_time:.3f}s",
            style="dim",
        )

    return _CellScanResult(
        result=result,
        action_label=action_label,
        item_label=item_label,
        action_taken=action_taken,
    )


def _record_processed_cell(
    *,
    page: int,
    cell: Cell,
    cell_scan: _CellScanResult,
    state: _ScanRunState,
    progress_impl: Optional[ScanProgress],
    items_total: Optional[int],
    pages_to_scan: int,
) -> None:
    state.results.append(cell_scan.result)
    if progress_impl is None:
        return

    processed = len(state.results)
    total_label = str(items_total) if items_total is not None else "?"
    current_label = (
        f"{processed}/{total_label} • p{page + 1}/{pages_to_scan} "
        f"r{cell.row}c{cell.col}"
    )
    progress_impl.update_item(
        current_label,
        cell_scan.item_label,
        cell_scan.action_label,
    )


def _update_stop_from_empty_detection(
    *,
    page: int,
    cells: List[Cell],
    context: _ScanContext,
    state: _ScanRunState,
    pages_to_scan: int,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
) -> None:
    empty_idx = _detect_consecutive_empty_stop_idx(
        page,
        cells,
        context.cells_per_page,
        context.win_left,
        context.win_top,
        context.win_width,
        context.win_height,
        context.safe_point_abs,
        context.stop_key,
        context.timing.action_delay,
    )
    if empty_idx is None:
        return
    if state.stop_at_global_idx is not None and empty_idx >= state.stop_at_global_idx:
        return

    state.stop_at_global_idx = empty_idx
    first_empty_idx = max(0, empty_idx - 1)
    detected_page = empty_idx // context.cells_per_page
    detected_cell = empty_idx % context.cells_per_page
    _queue_event(
        progress_impl,
        startup_events,
        f"Detected 2 consecutive empty slots at idx={first_empty_idx:03d},{empty_idx:03d} "
        f"(page {detected_page + 1}/{pages_to_scan}, cell {detected_cell})",
        style="yellow",
    )


def _scan_cells_on_page(
    *,
    page: int,
    cells: List[Cell],
    context: _ScanContext,
    state: _ScanRunState,
    infobox_retries: int,
    ocr_unreadable_retries: int,
    profile_timing: bool,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
    items_total: Optional[int],
    pages_to_scan: int,
) -> None:
    if not cells:
        return

    idx_in_page = 0
    open_cell_menu(
        cells[0],
        context.win_left,
        context.win_top,
        stop_key=context.stop_key,
        pause=context.timing.action_delay,
    )

    stop_scan = False
    while idx_in_page < len(cells):
        cell = cells[idx_in_page]
        global_idx = page * context.cells_per_page + cell.index

        if _should_stop_at_index(
            global_idx=global_idx,
            stop_at_global_idx=state.stop_at_global_idx,
            progress_impl=progress_impl,
            startup_events=startup_events,
        ):
            stop_scan = True
            break

        cell_scan = _process_cell(
            page=page,
            cell=cell,
            context=context,
            infobox_retries=infobox_retries,
            ocr_unreadable_retries=ocr_unreadable_retries,
            profile_timing=profile_timing,
            progress_impl=progress_impl,
            startup_events=startup_events,
        )
        _record_processed_cell(
            page=page,
            cell=cell,
            cell_scan=cell_scan,
            state=state,
            progress_impl=progress_impl,
            items_total=items_total,
            pages_to_scan=pages_to_scan,
        )

        destructive_action = cell_scan.action_taken in {"SELL", "RECYCLE"}
        if destructive_action:
            # Item removed; the next item collapses into this slot. Re-open the same cell.
            open_cell_menu(
                cell,
                context.win_left,
                context.win_top,
                stop_key=context.stop_key,
                pause=context.timing.action_delay,
            )
            continue

        idx_in_page += 1
        if idx_in_page < len(cells):
            next_global_idx = page * context.cells_per_page + cells[idx_in_page].index
            if _should_stop_at_index(
                global_idx=next_global_idx,
                stop_at_global_idx=state.stop_at_global_idx,
                progress_impl=progress_impl,
                startup_events=startup_events,
            ):
                stop_scan = True
                break
            open_cell_menu(
                cells[idx_in_page],
                context.win_left,
                context.win_top,
                stop_key=context.stop_key,
                pause=context.timing.action_delay,
            )

        if stop_scan:
            break


def _scan_single_page(
    *,
    page: int,
    initial_cells: List[Cell],
    scroll_sequence: Iterable[int],
    context: _ScanContext,
    state: _ScanRunState,
    infobox_retries: int,
    ocr_unreadable_retries: int,
    profile_timing: bool,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
    items_total: Optional[int],
    pages_to_scan: int,
) -> None:
    state.pages_scanned += 1

    cells = initial_cells
    if page > 0:
        clicks = next(scroll_sequence)
        scroll_to_next_grid_at(
            clicks,
            context.grid_center_abs,
            context.safe_point_abs,
            stop_key=context.stop_key,
            pause=context.timing.action_delay,
        )
        grid = _detect_grid(context, progress_impl, startup_events)
        cells = list(grid)

    _update_stop_from_empty_detection(
        page=page,
        cells=cells,
        context=context,
        state=state,
        pages_to_scan=pages_to_scan,
        progress_impl=progress_impl,
        startup_events=startup_events,
    )
    _scan_cells_on_page(
        page=page,
        cells=cells,
        context=context,
        state=state,
        infobox_retries=infobox_retries,
        ocr_unreadable_retries=ocr_unreadable_retries,
        profile_timing=profile_timing,
        progress_impl=progress_impl,
        startup_events=startup_events,
        items_total=items_total,
        pages_to_scan=pages_to_scan,
    )


def _scan_pages(
    *,
    context: _ScanContext,
    initial_cells: List[Cell],
    pages_to_scan: int,
    scroll_clicks_per_page: int,
    scroll_clicks_alt_per_page: int,
    infobox_retries: int,
    ocr_unreadable_retries: int,
    profile_timing: bool,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
    items_total: Optional[int],
) -> _ScanRunState:
    state = _ScanRunState()
    scroll_sequence = _scroll_clicks_sequence(
        scroll_clicks_per_page,
        scroll_clicks_alt_per_page,
    )

    for page in range(pages_to_scan):
        page_base_idx = page * context.cells_per_page
        if (
            state.stop_at_global_idx is not None
            and page_base_idx >= state.stop_at_global_idx
        ):
            break
        _scan_single_page(
            page=page,
            initial_cells=initial_cells,
            scroll_sequence=scroll_sequence,
            context=context,
            state=state,
            infobox_retries=infobox_retries,
            ocr_unreadable_retries=ocr_unreadable_retries,
            profile_timing=profile_timing,
            progress_impl=progress_impl,
            startup_events=startup_events,
            items_total=items_total,
            pages_to_scan=pages_to_scan,
        )

    return state


def scan_inventory(
    window_timeout: float = WINDOW_TIMEOUT,
    infobox_retries: int = INFOBOX_RETRIES,
    infobox_retry_delay_ms: int = int(INFOBOX_RETRY_DELAY * 1000),
    ocr_unreadable_retries: int = 1,
    ocr_unreadable_retry_delay_ms: int = 100,
    stop_key: str = DEFAULT_STOP_KEY,
    action_delay_ms: int = int(ACTION_DELAY * 1000),
    menu_appear_delay_ms: int = int(MENU_APPEAR_DELAY * 1000),
    sell_recycle_post_delay_ms: int = int(SELL_RECYCLE_POST_DELAY * 1000),
    show_progress: bool = True,
    pages: Optional[int] = None,
    scroll_clicks_per_page: int = SCROLL_CLICKS_PER_PAGE,
    scroll_clicks_alt_per_page: int = SCROLL_ALT_CLICKS_PER_PAGE,
    apply_actions: bool = True,
    actions_path: Path = ITEM_RULES_PATH,
    actions_override: Optional[ActionMap] = None,
    profile_timing: bool = False,
    progress: Optional[ScanProgress] = None,
) -> Tuple[List[ItemActionResult], ScanStats]:
    """
    Walk each 4x5 grid (top-to-bottom, left-to-right), OCR each cell's item
    title, and apply the configured keep/recycle/sell decision when possible.
    Decisions come from the default rules file unless a custom rules file exists
    or an override map is provided.
    Cells are detected via contours inside a normalized ROI, and scrolling
    alternates between `scroll_clicks_per_page` and `scroll_clicks_alt_per_page`
    to handle carousel offset. If `pages` is not provided, the script will
    OCR the always-visible stash count label to automatically determine how
    many 4x5 grids to scan.
    """
    _validate_scan_args(
        infobox_retries=infobox_retries,
        infobox_retry_delay_ms=infobox_retry_delay_ms,
        ocr_unreadable_retries=ocr_unreadable_retries,
        ocr_unreadable_retry_delay_ms=ocr_unreadable_retry_delay_ms,
        action_delay_ms=action_delay_ms,
        menu_appear_delay_ms=menu_appear_delay_ms,
        sell_recycle_post_delay_ms=sell_recycle_post_delay_ms,
        pages=pages,
        scroll_clicks_per_page=scroll_clicks_per_page,
        scroll_clicks_alt_per_page=scroll_clicks_alt_per_page,
    )

    stop_key = normalize_stop_key(stop_key)
    timing = _build_timing_config(
        action_delay_ms=action_delay_ms,
        menu_appear_delay_ms=menu_appear_delay_ms,
        infobox_retry_delay_ms=infobox_retry_delay_ms,
        sell_recycle_post_delay_ms=sell_recycle_post_delay_ms,
        ocr_unreadable_retry_delay_ms=ocr_unreadable_retry_delay_ms,
    )

    scan_start = time.perf_counter()

    _ocr_info = initialize_ocr()

    progress_impl = _build_progress_impl(show_progress, progress)
    if progress_impl is not None:
        progress_impl.start()
        progress_impl.set_phase("Waiting for Arc Raiders window…")

    try:
        if progress_impl is not None:
            window = wait_for_target_window(timeout=window_timeout, stop_key=stop_key)
        else:
            print("waiting for Arc Raiders to be active window...", flush=True)
            window = wait_for_target_window(timeout=window_timeout, stop_key=stop_key)

        _display_name, _display_size, work_area = window_display_info(window)
        mon_left, mon_top, mon_right, mon_bottom = window_monitor_rect(window)

        win_left, win_top, win_width, win_height = window_rect(window)
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
            action_delay=timing.action_delay,
            startup_events=startup_events,
        )
        auto_pages = (
            math.ceil(stash_items / cells_per_page) if stash_items is not None else None
        )
        pages_to_scan = pages if pages is not None else auto_pages or 1
        pages_to_scan = max(1, pages_to_scan)
        pages_source = "cli" if pages is not None else "auto"
        items_label = stash_items if stash_items is not None else "?"

        context = _ScanContext(
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

        grid = _detect_grid(context, progress_impl, startup_events)
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

        run_state = _scan_pages(
            context=context,
            initial_cells=cells,
            pages_to_scan=pages_to_scan,
            scroll_clicks_per_page=scroll_clicks_per_page,
            scroll_clicks_alt_per_page=scroll_clicks_alt_per_page,
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


# ---------------------------------------------------------------------------
# Empty cell detection
# ---------------------------------------------------------------------------


def _detect_consecutive_empty_stop_idx(
    page: int,
    cells: List[Cell],
    cells_per_page: int,
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
    safe_point_abs: Tuple[int, int],
    stop_key: str,
    action_delay: float,
) -> Optional[int]:
    """
    Capture the current page and return the global index of the *second* empty cell
    in the first run of two consecutive empty cells (row-major order).

    This is a pragmatic compromise: a single empty cell can be a transient gap
    (e.g., during item removal/collapse), but two empties in a row is a strong
    signal that we've reached the end of items.
    """
    abort_if_escape_pressed(stop_key)

    # Keep the cursor out of the grid so it doesn't occlude cells.
    move_absolute(safe_point_abs[0], safe_point_abs[1], stop_key=stop_key)
    pause_action(action_delay, stop_key=stop_key)

    window_bgr = capture_region((window_left, window_top, window_width, window_height))

    prev_empty = False
    for cell in cells:
        abort_if_escape_pressed(stop_key)
        x, y, w, h = cell.safe_rect
        slot_bgr = window_bgr[y : y + h, x : x + w]
        if slot_bgr.size == 0:
            prev_empty = False
            continue
        is_empty = is_slot_empty(slot_bgr)
        if is_empty and prev_empty:
            return page * cells_per_page + cell.index
        prev_empty = is_empty

    return None
