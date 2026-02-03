from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

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


def _scroll_clicks_sequence(start_clicks: int) -> Iterable[int]:
    """
    Yield alternating scroll counts: start_clicks, start_clicks + 1, repeat.
    """
    base = abs(start_clicks)
    alt = base + 1
    use_alt = False
    while True:
        yield alt if use_alt else base
        use_alt = not use_alt


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
    alternates between `scroll_clicks_per_page` and `scroll_clicks_per_page + 1`
    to handle the carousel offset. If `pages` is not provided, the script will
    OCR the always-visible stash count label to automatically determine how
    many 4x5 grids to scan.
    """
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

    stop_key = normalize_stop_key(stop_key)
    action_delay = action_delay_ms / 1000.0
    menu_appear_delay = menu_appear_delay_ms / 1000.0
    infobox_retry_delay = infobox_retry_delay_ms / 1000.0
    post_action_delay = sell_recycle_post_delay_ms / 1000.0

    scan_start = time.perf_counter()

    _ocr_info = initialize_ocr()

    progress_impl: Optional[ScanProgress] = progress
    if progress_impl is None and show_progress and Console is not None:
        try:
            progress_impl = RichScanProgress()
        except Exception:
            progress_impl = None

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

        def _detect_inventory_count() -> Tuple[Optional[int], str]:
            """
            Capture the stash count label while the cursor is in a safe spot.
            """
            try:
                move_absolute(
                    safe_point_abs[0],
                    safe_point_abs[1],
                    stop_key=stop_key,
                )
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

        stash_items, stash_count_text = _detect_inventory_count()
        auto_pages = (
            math.ceil(stash_items / cells_per_page) if stash_items is not None else None
        )
        pages_to_scan = pages if pages is not None else auto_pages or 1
        pages_to_scan = max(1, pages_to_scan)
        pages_source = "cli" if pages is not None else "auto"
        items_label = stash_items if stash_items is not None else "?"

        def _queue_event(message: str, style: str = "dim") -> None:
            if progress_impl is not None:
                progress_impl.add_event(message, style=style)
            else:
                startup_events.append((message, style))

        def _detect_grid() -> Grid:
            """
            Move the cursor out of the grid, capture the ROI, and detect cells.
            """
            move_absolute(
                safe_point_abs[0],
                safe_point_abs[1],
                stop_key=stop_key,
            )
            pause_action(action_delay, stop_key=stop_key)
            roi_left = win_left + grid_roi[0]
            roi_top = win_top + grid_roi[1]
            inv_bgr = capture_region((roi_left, roi_top, grid_roi[2], grid_roi[3]))
            grid = Grid.detect(inv_bgr, grid_roi, win_width, win_height)
            expected_cells = Grid.COLS * Grid.ROWS
            if len(grid) < expected_cells:
                _queue_event(
                    f"Detected {len(grid)} cells inside the grid ROI (expected {expected_cells}); "
                    "grid may be partially obscured or ROI misaligned.",
                    style="yellow",
                )
            return grid

        grid = _detect_grid()
        cells = list(grid)
        total_cells = cells_per_page * pages_to_scan
        items_total = stash_items if stash_items is not None else total_cells
        results: List[ItemActionResult] = []
        pages_scanned = 0

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

        stop_at_global_idx: Optional[int] = None
        scroll_sequence = _scroll_clicks_sequence(scroll_clicks_per_page)
        stop_scan = False

        for page in range(pages_to_scan):
            page_base_idx = page * cells_per_page
            if stop_at_global_idx is not None and page_base_idx >= stop_at_global_idx:
                break

            pages_scanned += 1
            if page > 0:
                clicks = next(scroll_sequence)
                scroll_to_next_grid_at(
                    clicks,
                    grid_center_abs,
                    safe_point_abs,
                    stop_key=stop_key,
                    pause=action_delay,
                )
                grid = _detect_grid()
                cells = list(grid)

            empty_idx = _detect_consecutive_empty_stop_idx(
                page,
                cells,
                cells_per_page,
                win_left,
                win_top,
                win_width,
                win_height,
                safe_point_abs,
                stop_key,
                action_delay,
            )
            if empty_idx is not None and (
                stop_at_global_idx is None or empty_idx < stop_at_global_idx
            ):
                stop_at_global_idx = empty_idx
                first_empty_idx = max(0, empty_idx - 1)
                detected_page = empty_idx // cells_per_page
                detected_cell = empty_idx % cells_per_page
                _queue_event(
                    f"Detected 2 consecutive empty slots at idx={first_empty_idx:03d},{empty_idx:03d} "
                    f"(page {detected_page + 1}/{pages_to_scan}, cell {detected_cell})",
                    style="yellow",
                )

            if not cells:
                continue

            idx_in_page = 0
            open_cell_menu(
                cells[0],
                win_left,
                win_top,
                stop_key=stop_key,
                pause=action_delay,
            )

            while idx_in_page < len(cells):
                cell = cells[idx_in_page]
                global_idx = page * cells_per_page + cell.index
                cell_start = time.perf_counter()

                if stop_at_global_idx is not None and global_idx >= stop_at_global_idx:
                    _queue_event(
                        f"Reached empty slot idx={stop_at_global_idx:03d}; stopping scan.",
                        style="yellow",
                    )
                    if progress_impl is not None:
                        progress_impl.set_phase("Stopping…")
                    stop_scan = True
                    break

                abort_if_escape_pressed(stop_key)
                if hasattr(window, "isAlive") and not window.isAlive:  # type: ignore[attr-defined]
                    raise RuntimeError("Target window closed during scan")

                sleep_with_abort(menu_appear_delay, stop_key=stop_key)
                pause_action(action_delay, stop_key=stop_key)

                infobox_rect: Optional[Tuple[int, int, int, int]] = None
                window_bgr = None
                infobox_ocr = None
                sell_bbox_rel: Optional[Tuple[int, int, int, int]] = None
                recycle_bbox_rel: Optional[Tuple[int, int, int, int]] = None
                capture_time = 0.0
                ocr_time = 0.0
                preprocess_time = 0.0
                find_time = 0.0
                capture_attempts = 0
                found_on_attempt = 0
                raw_item_text = ""

                for attempt in range(1, infobox_retries + 1):
                    capture_attempts += 1
                    abort_if_escape_pressed(stop_key)
                    capture_start = time.perf_counter()
                    window_bgr = capture_region(
                        (win_left, win_top, win_width, win_height)
                    )
                    capture_time += time.perf_counter() - capture_start
                    find_start = time.perf_counter()
                    infobox_rect = find_infobox(window_bgr)
                    find_time += time.perf_counter() - find_start
                    if infobox_rect:
                        found_on_attempt = attempt
                        break
                    sleep_with_abort(infobox_retry_delay, stop_key=stop_key)
                    pause_action(action_delay, stop_key=stop_key)

                item_name = ""
                if infobox_rect and window_bgr is not None:
                    pause_action(action_delay, stop_key=stop_key)
                    x, y, w, h = infobox_rect
                    delay_seconds = ocr_unreadable_retry_delay_ms / 1000.0

                    for ocr_attempt in range(ocr_unreadable_retries + 1):
                        if ocr_attempt > 0:
                            sleep_with_abort(delay_seconds, stop_key=stop_key)
                            try:
                                infobox_bgr = capture_region(
                                    (win_left + x, win_top + y, w, h)
                                )
                            except Exception:
                                window_bgr = capture_region(
                                    (win_left, win_top, win_width, win_height)
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

                decision: Optional[Decision] = None
                decision_note: Optional[str] = None
                action_taken = "SCAN_ONLY"

                if actions and item_name:
                    decision, decision_note = choose_decision(item_name, actions)

                if decision is None:
                    if not item_name:
                        if infobox_rect is None:
                            action_taken = "UNREADABLE_NO_INFOBOX"
                        elif infobox_ocr is None:
                            action_taken = "UNREADABLE_NO_OCR"
                        elif infobox_ocr.ocr_failed:
                            action_taken = "UNREADABLE_OCR_FAILED"
                        else:
                            action_taken = "UNREADABLE_TITLE"
                    elif not actions:
                        action_taken = "SKIP_NO_ACTION_MAP"
                    else:
                        action_taken = "SKIP_UNLISTED"
                elif decision == "KEEP":
                    action_taken = decision
                elif decision == "SELL":
                    if infobox_rect is not None and infobox_ocr is not None:
                        if sell_bbox_rel is None:
                            action_taken = "SKIP_NO_ACTION_BBOX"
                        elif apply_actions:
                            _perform_sell(
                                infobox_rect,
                                sell_bbox_rel,
                                win_left,
                                win_top,
                                win_width,
                                win_height,
                                stop_key=stop_key,
                                action_delay=action_delay,
                                menu_appear_delay=menu_appear_delay,
                                post_action_delay=post_action_delay,
                            )
                            action_taken = "SELL"
                        else:
                            action_taken = "DRY_RUN_SELL"
                    else:
                        action_taken = "SKIP_NO_INFOBOX"
                elif decision == "RECYCLE":
                    if infobox_rect is not None and infobox_ocr is not None:
                        if recycle_bbox_rel is None:
                            action_taken = "SKIP_NO_ACTION_BBOX"
                        elif apply_actions:
                            _perform_recycle(
                                infobox_rect,
                                recycle_bbox_rel,
                                win_left,
                                win_top,
                                win_width,
                                win_height,
                                stop_key=stop_key,
                                action_delay=action_delay,
                                menu_appear_delay=menu_appear_delay,
                                post_action_delay=post_action_delay,
                            )
                            action_taken = "RECYCLE"
                        else:
                            action_taken = "DRY_RUN_RECYCLE"
                    else:
                        action_taken = "SKIP_NO_INFOBOX"

                action_label, details = _describe_action(action_taken)
                item_label = (
                    (item_name or raw_item_text or "<unreadable>")
                    .replace("\n", " ")
                    .strip()
                )

                results.append(
                    ItemActionResult(
                        page=page,
                        cell=cell,
                        item_name=item_name,
                        decision=decision,
                        action_taken=action_taken,
                        raw_item_text=raw_item_text or None,
                        note=decision_note,
                    )
                )

                if progress_impl is not None:
                    processed = len(results)
                    total_label = str(items_total) if items_total is not None else "?"
                    current_label = (
                        f"{processed}/{total_label} • p{page + 1}/{pages_to_scan} "
                        f"r{cell.row}c{cell.col}"
                    )
                    progress_impl.update_item(current_label, item_label, action_label)

                destructive_action = action_taken in {"SELL", "RECYCLE"}
                if destructive_action:
                    # Item removed; the next item collapses into this slot. Re-open the same cell.
                    open_cell_menu(
                        cell,
                        win_left,
                        win_top,
                        stop_key=stop_key,
                        pause=action_delay,
                    )
                    continue

                if profile_timing:
                    total_time = time.perf_counter() - cell_start
                    _queue_event(
                        f"Perf idx={global_idx:03d} • tries={capture_attempts} • found@{found_on_attempt} • "
                        f"infobox={'y' if infobox_rect else 'n'}\n"
                        f"  cap {capture_time:.3f}s • find {find_time:.3f}s • pre {preprocess_time:.3f}s • "
                        f"ocr {ocr_time:.3f}s • total {total_time:.3f}s",
                        style="dim",
                    )

                idx_in_page += 1
                if idx_in_page < len(cells):
                    next_global_idx = page * cells_per_page + cells[idx_in_page].index
                    if (
                        stop_at_global_idx is not None
                        and next_global_idx >= stop_at_global_idx
                    ):
                        _queue_event(
                            f"Reached empty slot idx={stop_at_global_idx:03d}; stopping scan.",
                            style="yellow",
                        )
                        if progress_impl is not None:
                            progress_impl.set_phase("Stopping…")
                        stop_scan = True
                        break
                    open_cell_menu(
                        cells[idx_in_page],
                        win_left,
                        win_top,
                        stop_key=stop_key,
                        pause=action_delay,
                    )

                if stop_scan:
                    break
        processing_seconds = time.perf_counter() - scan_start
        stats = ScanStats(
            items_in_stash=stash_items,
            stash_count_text=stash_count_text,
            pages_planned=pages_to_scan,
            pages_scanned=pages_scanned,
            processing_seconds=processing_seconds,
        )

        return results, stats
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
