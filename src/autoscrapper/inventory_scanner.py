"""
inventory_scanner.py

Scan the 4x6 inventory grid by hovering each cell, opening the context
menu, locating the light infobox (#f9eedf), and OCR-ing the item title.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

try:
    from tqdm.auto import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None

try:
    from rich import box
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - optional dependency
    Console = None
    Table = None
    Text = None
    box = None

from .interaction.inventory_grid import (
    Cell,
    Grid,
    grid_center_point,
    inventory_roi_rect,
    safe_mouse_point,
)
from .core.item_actions import (
    ActionMap,
    Decision,
    ITEM_ACTIONS_PATH,
    ItemActionResult,
    choose_decision,
    load_item_actions,
)
from .interaction.ui_windows import (
    SCROLL_CLICKS_PER_PAGE,
    SELL_RECYCLE_ACTION_DELAY,
    SELL_RECYCLE_MOVE_DURATION,
    SELL_RECYCLE_POST_DELAY,
    WINDOW_TIMEOUT,
    abort_if_escape_pressed,
    capture_region,
    click_absolute,
    click_window_relative,
    move_absolute,
    move_window_relative,
    open_cell_menu,
    pause_action,
    scroll_to_next_grid_at,
    sleep_with_abort,
    wait_for_target_window,
    window_display_info,
    window_rect,
)
from .ocr.tesseract import initialize_ocr
from .ocr.inventory_vision import (
    enable_ocr_debug,
    find_infobox,
    inventory_count_rect,
    is_slot_empty,
    ocr_infobox,
    ocr_inventory_count,
    recycle_confirm_button_center,
    rect_center,
    sell_confirm_button_center,
)
from .config import load_scan_settings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MENU_APPEAR_DELAY = 0.05
INFOBOX_RETRY_DELAY = 0.05
INFOBOX_RETRIES = 3


@dataclass
class ScanStats:
    """
    Aggregate metrics for the scan useful for reporting.
    """

    items_in_stash: Optional[int]
    stash_count_text: str
    pages_planned: int
    pages_scanned: int
    processing_seconds: float


def _perform_sell(
    infobox_rect: Tuple[int, int, int, int],
    action_bbox_rel: Tuple[int, int, int, int],
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> None:
    bx, by, bw, bh = action_bbox_rel
    sell_bbox_win = (infobox_rect[0] + bx, infobox_rect[1] + by, bw, bh)
    sx, sy = rect_center(sell_bbox_win)
    move_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        label="sell",
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        label="sell",
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = sell_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        label="sell confirm",
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, label="sell confirm", pause=SELL_RECYCLE_ACTION_DELAY)
    sleep_with_abort(SELL_RECYCLE_POST_DELAY)


def _perform_recycle(
    infobox_rect: Tuple[int, int, int, int],
    action_bbox_rel: Tuple[int, int, int, int],
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> None:
    bx, by, bw, bh = action_bbox_rel
    recycle_bbox_win = (infobox_rect[0] + bx, infobox_rect[1] + by, bw, bh)
    rx, ry = rect_center(recycle_bbox_win)
    move_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        label="recycle",
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        label="recycle",
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = recycle_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        label="recycle confirm",
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, label="recycle confirm", pause=SELL_RECYCLE_ACTION_DELAY)
    sleep_with_abort(SELL_RECYCLE_POST_DELAY)


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
    ocr_unreadable_retries: int = 1,
    ocr_unreadable_retry_delay_ms: int = 100,
    show_progress: bool = True,
    pages: Optional[int] = None,
    scroll_clicks_per_page: int = SCROLL_CLICKS_PER_PAGE,
    apply_actions: bool = True,
    actions_path: Path = ITEM_ACTIONS_PATH,
    actions_override: Optional[ActionMap] = None,
    profile_timing: bool = False,
) -> Tuple[List[ItemActionResult], ScanStats]:
    """
    Walk each 6x4 grid (top-to-bottom, left-to-right), OCR each cell's item
    title, and apply the configured keep/recycle/sell decision when possible.
    Decisions come from items_actions.json unless an override map is provided.
    Cells are detected via contours inside a normalized ROI, and scrolling
    alternates between `scroll_clicks_per_page` and `scroll_clicks_per_page + 1`
    to handle the carousel offset. If `pages` is not provided, the script will
    OCR the always-visible stash count label to automatically determine how
    many 6x4 grids to scan.
    """
    if infobox_retries < 1:
        raise ValueError("infobox_retries must be >= 1")
    if ocr_unreadable_retries < 0:
        raise ValueError("ocr_unreadable_retries must be >= 0")
    if ocr_unreadable_retry_delay_ms < 0:
        raise ValueError("ocr_unreadable_retry_delay_ms must be >= 0")
    if pages is not None and pages < 1:
        raise ValueError("pages must be >= 1")

    scan_start = time.perf_counter()

    print("waiting for Arc Raiders to be active window...", flush=True)
    window = wait_for_target_window(timeout=window_timeout)
    display_name, display_size, work_area = window_display_info(window)
    win_left, win_top, win_width, win_height = window_rect(window)
    win_right = win_left + win_width
    win_bottom = win_top + win_height
    work_left, work_top, work_right, work_bottom = work_area

    print(
        f"[display] {display_name} size={display_size[0]}x{display_size[1]} "
        f"work_area=({work_left},{work_top},{work_right},{work_bottom})",
        flush=True,
    )
    print(
        f"[window] pos=({win_left},{win_top}) size={win_width}x{win_height}",
        flush=True,
    )
    if (
        win_left < work_left
        or win_top < work_top
        or win_right > work_right
        or win_bottom > work_bottom
    ):
        print(
            "[warning] target window extends beyond its display's work area; "
            "ensure it is fully visible on a single monitor.",
            flush=True,
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
                label="move to safe area for stash count",
            )
            pause_action()
            count_roi_rel = inventory_count_rect(win_width, win_height)
            count_left = win_left + count_roi_rel[0]
            count_top = win_top + count_roi_rel[1]
            count_bgr = capture_region(
                (count_left, count_top, count_roi_rel[2], count_roi_rel[3])
            )
            return ocr_inventory_count(count_bgr)
        except Exception as exc:
            print(f"[warning] failed to read stash count: {exc}", flush=True)
            return None, ""

    stash_items, stash_count_text = _detect_inventory_count()
    auto_pages = (
        math.ceil(stash_items / cells_per_page) if stash_items is not None else None
    )
    pages_to_scan = pages if pages is not None else auto_pages or 1
    pages_to_scan = max(1, pages_to_scan)
    pages_source = "cli" if pages is not None else "auto"
    items_label = stash_items if stash_items is not None else "?"
    count_label = f" raw='{stash_count_text}'" if stash_count_text else ""
    print(
        f"[count] items_in_stash={items_label} pages_to_scan={pages_to_scan} "
        f"(cells/page={cells_per_page}) source={pages_source}{count_label}",
        flush=True,
    )

    def _detect_grid() -> Grid:
        """
        Move the cursor out of the grid, capture the ROI, and detect cells.
        """
        move_absolute(
            safe_point_abs[0],
            safe_point_abs[1],
            label="move to safe area for detection",
        )
        pause_action()
        roi_left = win_left + grid_roi[0]
        roi_top = win_top + grid_roi[1]
        inv_bgr = capture_region((roi_left, roi_top, grid_roi[2], grid_roi[3]))
        grid = Grid.detect(inv_bgr, grid_roi, win_width, win_height)
        expected_cells = Grid.COLS * Grid.ROWS
        if len(grid) < expected_cells:
            print(
                f"[warning] detected {len(grid)} cells inside the grid ROI (expected {expected_cells}); "
                "grid may be partially obscured or ROI misaligned.",
                flush=True,
            )
        return grid

    grid = _detect_grid()
    cells = list(grid)
    total_cells = cells_per_page * pages_to_scan
    results: List[ItemActionResult] = []
    pages_scanned = 0

    abort_if_escape_pressed()

    progress = (
        tqdm(total=total_cells, desc="Scanning grid")
        if show_progress and tqdm is not None
        else None
    )
    stop_at_global_idx: Optional[int] = None
    scroll_sequence = _scroll_clicks_sequence(scroll_clicks_per_page)
    stop_scan = False

    try:
        for page in range(pages_to_scan):
            page_base_idx = page * cells_per_page
            if stop_at_global_idx is not None and page_base_idx >= stop_at_global_idx:
                break

            pages_scanned += 1
            if page > 0:
                clicks = next(scroll_sequence)
                scroll_to_next_grid_at(clicks, grid_center_abs, safe_point_abs)
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
            )
            if empty_idx is not None and (
                stop_at_global_idx is None or empty_idx < stop_at_global_idx
            ):
                stop_at_global_idx = empty_idx
                first_empty_idx = max(0, empty_idx - 1)
                detected_page = empty_idx // cells_per_page
                detected_cell = empty_idx % cells_per_page
                print(
                    f"[empty] 2 consecutive empty cells detected at idx={first_empty_idx:03d},{empty_idx:03d} "
                    f"page={detected_page + 1:02d} cell={detected_cell:02d}"
                )

            if not cells:
                continue

            idx_in_page = 0
            open_cell_menu(cells[0], win_left, win_top)

            while idx_in_page < len(cells):
                cell = cells[idx_in_page]
                global_idx = page * cells_per_page + cell.index
                cell_start = time.perf_counter()

                if stop_at_global_idx is not None and global_idx >= stop_at_global_idx:
                    print(
                        f"[empty] reached empty cell idx={stop_at_global_idx:03d}; stopping scan."
                    )
                    stop_scan = True
                    break

                abort_if_escape_pressed()
                if hasattr(window, "isAlive") and not window.isAlive:  # type: ignore[attr-defined]
                    raise RuntimeError("Target window closed during scan")

                time.sleep(MENU_APPEAR_DELAY)
                pause_action()

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
                    abort_if_escape_pressed()
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
                    time.sleep(INFOBOX_RETRY_DELAY)
                    pause_action()

                item_name = ""
                if infobox_rect and window_bgr is not None:
                    pause_action()
                    x, y, w, h = infobox_rect
                    delay_seconds = ocr_unreadable_retry_delay_ms / 1000.0

                    for ocr_attempt in range(ocr_unreadable_retries + 1):
                        if ocr_attempt > 0:
                            sleep_with_abort(delay_seconds)
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
                elif decision in {"KEEP", "CRAFTING MATERIAL"}:
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
                            )
                            action_taken = "RECYCLE"
                        else:
                            action_taken = "DRY_RUN_RECYCLE"
                    else:
                        action_taken = "SKIP_NO_INFOBOX"

                note_suffix = f" note={decision_note}" if decision_note else ""
                infobox_status = "found" if infobox_rect else "missing"
                action_label, details = _describe_action(action_taken)
                if action_label == "SKIP":
                    action_label = "SKIPPED"
                detail_suffix = f" detail={'; '.join(details)}" if details else ""
                item_label = item_name or raw_item_text or "<unreadable>"
                print(
                    f"[item] idx={global_idx:03d} page={page + 1:02d} cell={cell.index:02d} "
                    f"item='{item_label}' action={action_label}{detail_suffix} "
                    f"infobox={infobox_status}{note_suffix}"
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

                destructive_action = action_taken in {"SELL", "RECYCLE"}
                if destructive_action:
                    # Item removed; the next item collapses into this slot. Re-open the same cell.
                    open_cell_menu(cell, win_left, win_top)
                    continue

                if progress:
                    progress.update(1)

                if profile_timing:
                    total_time = time.perf_counter() - cell_start
                    print(
                        f"[perf] idx={global_idx:03d} capture={capture_time:.3f}s "
                        f"find={find_time:.3f}s preprocess={preprocess_time:.3f}s "
                        f"ocr={ocr_time:.3f}s total={total_time:.3f}s "
                        f"tries={capture_attempts} found_at={found_on_attempt} "
                        f"infobox={'y' if infobox_rect else 'n'}"
                    )

                idx_in_page += 1
                if idx_in_page < len(cells):
                    next_global_idx = page * cells_per_page + cells[idx_in_page].index
                    if (
                        stop_at_global_idx is not None
                        and next_global_idx >= stop_at_global_idx
                    ):
                        print(
                            f"[empty] reached empty cell idx={stop_at_global_idx:03d}; stopping scan."
                        )
                        stop_scan = True
                        break
                    open_cell_menu(cells[idx_in_page], win_left, win_top)

            if stop_scan:
                break
    finally:
        if progress:
            progress.close()

    processing_seconds = time.perf_counter() - scan_start
    stats = ScanStats(
        items_in_stash=stash_items,
        stash_count_text=stash_count_text,
        pages_planned=pages_to_scan,
        pages_scanned=pages_scanned,
        processing_seconds=processing_seconds,
    )

    return results, stats


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
) -> Optional[int]:
    """
    Capture the current page and return the global index of the *second* empty cell
    in the first run of two consecutive empty cells (row-major order).

    This is a pragmatic compromise: a single empty cell can be a transient gap
    (e.g., during item removal/collapse), but two empties in a row is a strong
    signal that we've reached the end of items.
    """
    abort_if_escape_pressed()

    # Keep the cursor out of the grid so it doesn't occlude cells.
    move_absolute(
        safe_point_abs[0], safe_point_abs[1], label="clear for empty detection"
    )
    pause_action()

    window_bgr = capture_region((window_left, window_top, window_width, window_height))

    prev_empty = False
    for cell in cells:
        abort_if_escape_pressed()
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


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_UNREADABLE_REASONS = {
    "UNREADABLE_NO_INFOBOX": "infobox missing",
    "UNREADABLE_NO_OCR": "ocr not run",
    "UNREADABLE_OCR_FAILED": "ocr failed",
    "UNREADABLE_TITLE": "title unreadable",
}

_SKIP_REASONS = {
    "SKIP_NO_NAME": "missing OCR name",
    "SKIP_NO_ACTION_MAP": "no action map loaded",
    "SKIP_UNLISTED": "no configured decision",
    "SKIP_NO_ACTION_BBOX": "action not found in menu",
    "SKIP_NO_INFOBOX": "infobox missing",
}


def _describe_action(action_taken: str) -> Tuple[str, List[str]]:
    """
    Normalize the action label (for display) and attach human-readable details.
    """
    details: List[str] = []
    if action_taken.startswith("SKIP_"):
        reason = _SKIP_REASONS.get(
            action_taken, action_taken.replace("SKIP_", "").replace("_", " ").lower()
        )
        details.append(reason)
        return "SKIP", details

    if action_taken.startswith("UNREADABLE_"):
        reason = _UNREADABLE_REASONS.get(
            action_taken,
            action_taken.replace("UNREADABLE_", "").replace("_", " ").lower(),
        )
        details.append(reason)
        return "UNREADABLE", details

    if action_taken.startswith("DRY_RUN_"):
        base = action_taken[len("DRY_RUN_") :]
        details.append("dry run")
        return f"DRY-{base}", details

    return action_taken, details


def _outcome_style(label: str) -> str:
    base = label.replace("DRY-", "")
    return {
        "KEEP": "green",
        "CRAFTING MATERIAL": "bright_blue",
        "RECYCLE": "cyan",
        "SELL": "magenta",
        "UNREADABLE": "yellow",
        "SKIP": "red",
    }.get(base, "white")


def _summarize_results(results: List[ItemActionResult]) -> Counter:
    summary = Counter()
    for result in results:
        label, _ = _describe_action(result.action_taken)
        summary[label] += 1
    return summary


def _render_scan_overview(
    results: List[ItemActionResult],
    stats: ScanStats,
    console: Optional["Console"],
) -> None:
    """
    Display high-level scan metrics (stash total, processed count, pages, time).
    """
    items_processed = len(results)
    stash_label = str(stats.items_in_stash) if stats.items_in_stash is not None else "?"
    duration_label = f"{stats.processing_seconds:.1f}s"
    planned_suffix = (
        f" (planned {stats.pages_planned})"
        if stats.pages_planned != stats.pages_scanned
        else ""
    )
    raw_suffix = (
        f" raw='{stats.stash_count_text}'"
        if stats.stash_count_text and stats.items_in_stash is None
        else ""
    )

    if console is None:
        print(
            f"Overview: stash_items={stash_label} processed={items_processed} "
            f"pages_run={stats.pages_scanned}{planned_suffix} duration={duration_label}{raw_suffix}"
        )
        return

    table = Table(
        title="Inventory Overview",
        box=box.SIMPLE,
        show_header=False,
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Metric", justify="left", style="cyan", no_wrap=True)
    table.add_column("Value", justify="left", style="white")
    table.add_row("Items in stash", stash_label)
    table.add_row("Items processed", str(items_processed))
    pages_value = f"{stats.pages_scanned}"
    if planned_suffix:
        pages_value = f"{pages_value}{planned_suffix}"
    table.add_row("6x4 pages run", pages_value)
    table.add_row("Processing time", duration_label)
    if stats.items_in_stash is None and stats.stash_count_text:
        table.add_row("Count OCR", stats.stash_count_text)
    console.print(table)


def _render_summary(summary: Counter, console: Optional["Console"]) -> None:
    ordered_keys = [
        k for k in ("KEEP", "CRAFTING MATERIAL", "RECYCLE", "SELL") if k in summary
    ]
    ordered_keys += [k for k in ("DRY-KEEP", "DRY-RECYCLE", "DRY-SELL") if k in summary]
    if "UNREADABLE" in summary:
        ordered_keys.append("UNREADABLE")
    if "SKIP" in summary:
        ordered_keys.append("SKIP")
    ordered_keys += sorted(set(summary.keys()) - set(ordered_keys))

    parts = [f"{k}={summary[k]}" for k in ordered_keys]
    if console is None:
        print("Summary: " + ", ".join(parts))
        return

    table = Table(
        title="Summary",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Outcome", justify="left", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="white", no_wrap=True)
    for key in ordered_keys:
        label = Text(key, style=_outcome_style(key))
        table.add_row(label, str(summary[key]))
    console.print(table)


def _item_label(result: ItemActionResult) -> str:
    """
    Prefer cleaned OCR text, then raw OCR text, then fallback label.
    """
    return result.item_name or result.raw_item_text or "<unreadable>"


def _render_results(
    results: List[ItemActionResult], cells_per_page: int, stats: ScanStats
) -> None:
    console = (
        Console()
        if Console is not None
        and Table is not None
        and Text is not None
        and box is not None
        else None
    )
    summary = _summarize_results(results)

    _render_scan_overview(results, stats, console)

    if not results:
        if console is None:
            print("No results to display.")
        else:
            console.print()
            console.print("No results to display.")
        return

    if console is None:
        for result in results:
            label = _item_label(result)
            global_idx = result.page * cells_per_page + result.cell.index
            outcome_label, details = _describe_action(result.action_taken)
            if result.decision and not outcome_label.startswith(result.decision):
                details.append(f"plan {result.decision}")
            if result.note:
                details.append(result.note)
            notes = f" | {'; '.join(details)}" if details else ""
            print(
                f"p{result.page + 1:02d} idx={global_idx:03d} r{result.cell.row}c{result.cell.col} "
                f"| {label} | {outcome_label}{notes}"
            )
        _render_summary(summary, None)
        return

    console.print()
    table = Table(
        title="Inventory Scan Results",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold",
        show_lines=False,
        pad_edge=False,
    )
    table.add_column("Pg", justify="right", style="cyan", width=2, no_wrap=True)
    table.add_column("Idx", justify="right", style="cyan", width=3, no_wrap=True)
    table.add_column("Cell", justify="left", style="cyan", width=6, no_wrap=True)
    table.add_column("Item", justify="left", style="white", overflow="fold")
    table.add_column("Outcome", justify="center", style="white", no_wrap=True)
    table.add_column("Notes", justify="left", style="dim", overflow="fold")

    for result in results:
        label = _item_label(result)
        global_idx = result.page * cells_per_page + result.cell.index
        outcome_label, details = _describe_action(result.action_taken)
        if result.decision and not outcome_label.startswith(result.decision):
            details.append(f"plan {result.decision}")
        if result.note:
            details.append(result.note)
        notes = "; ".join(details)

        outcome_text = Text(outcome_label, style=_outcome_style(outcome_label))
        table.add_row(
            f"{result.page + 1:02d}",
            f"{global_idx:03d}",
            f"r{result.cell.row}c{result.cell.col}",
            label,
            outcome_text,
            notes,
        )

    console.print(table)
    _render_summary(summary, console)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _non_negative_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def main(argv: Optional[Iterable[str]] = None) -> int:
    settings = load_scan_settings()
    pages_default = settings.pages if settings.pages_mode == "manual" else None
    scroll_clicks_default = (
        settings.scroll_clicks_per_page
        if settings.scroll_clicks_per_page is not None
        else SCROLL_CLICKS_PER_PAGE
    )

    parser = argparse.ArgumentParser(
        description="Scan the ARC Raiders inventory grid(s)."
    )
    parser.add_argument(
        "--pages",
        type=_positive_int_arg,
        default=pages_default,
        help="Override auto-detected page count; number of 6x4 grids to scan.",
    )
    parser.add_argument(
        "--scroll-clicks",
        type=_non_negative_int_arg,
        default=scroll_clicks_default,
        help="Initial scroll clicks to reach the next grid (alternates with +1 on following page).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only; log planned actions without clicking sell/recycle.",
    )

    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument(
        "--profile",
        dest="profile",
        action="store_true",
        help="Log per-item timing (capture, OCR, total) to identify bottlenecks.",
    )
    profile_group.add_argument(
        "--no-profile",
        dest="profile",
        action="store_false",
        help="Disable per-item profiling (ignores saved scan configuration).",
    )
    parser.set_defaults(profile=settings.profile)

    debug_group = parser.add_mutually_exclusive_group()
    debug_group.add_argument(
        "--debug",
        "--debug-ocr",
        dest="debug_ocr",
        action="store_true",
        help="Save OCR input/processed images to ./ocr_debug for debugging.",
    )
    debug_group.add_argument(
        "--no-debug",
        dest="debug_ocr",
        action="store_false",
        help="Disable OCR debug images (ignores saved scan configuration).",
    )
    parser.set_defaults(debug_ocr=settings.debug_ocr)

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.debug_ocr:
        enable_ocr_debug(Path("ocr_debug"))

    try:
        initialize_ocr()
        results, stats = scan_inventory(
            show_progress=True,
            pages=args.pages,
            scroll_clicks_per_page=args.scroll_clicks,
            apply_actions=not args.dry_run,
            actions_path=ITEM_ACTIONS_PATH,
            profile_timing=args.profile,
            ocr_unreadable_retries=settings.ocr_unreadable_retries,
            ocr_unreadable_retry_delay_ms=settings.ocr_unreadable_retry_delay_ms,
        )
    except KeyboardInterrupt:
        print("Aborted by Escape key.")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    except TimeoutError as exc:
        print(exc)
        return 1
    except RuntimeError as exc:
        print(f"Fatal: {exc}")
        return 1

    cells_per_page = Grid.COLS * Grid.ROWS
    _render_results(results, cells_per_page, stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())
