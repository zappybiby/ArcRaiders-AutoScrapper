"""
inventory_scanner.py

Scan the 4x5 inventory grid by hovering each cell, opening the context
menu, locating the light infobox (#f9eedf), and OCR-ing the item title.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.console import Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn
    from rich.progress import Progress
    from rich.progress import ProgressColumn
    from rich.progress import SpinnerColumn
    from rich.progress import Task
    from rich.progress import TaskProgressColumn
    from rich.progress import TextColumn
    from rich.progress import TimeElapsedColumn
    from rich.progress import TimeRemainingColumn
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - optional dependency
    Align = None
    Console = None
    Group = None
    Live = None
    Panel = None
    BarColumn = None
    Progress = None
    ProgressColumn = None
    SpinnerColumn = None
    Task = None
    TaskProgressColumn = None
    TextColumn = None
    TimeElapsedColumn = None
    TimeRemainingColumn = None
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
    window_monitor_rect,
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
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = sell_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, pause=SELL_RECYCLE_ACTION_DELAY)
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
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = recycle_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, pause=SELL_RECYCLE_ACTION_DELAY)
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
    Walk each 4x5 grid (top-to-bottom, left-to-right), OCR each cell's item
    title, and apply the configured keep/recycle/sell decision when possible.
    Decisions come from items_actions.json unless an override map is provided.
    Cells are detected via contours inside a normalized ROI, and scrolling
    alternates between `scroll_clicks_per_page` and `scroll_clicks_per_page + 1`
    to handle the carousel offset. If `pages` is not provided, the script will
    OCR the always-visible stash count label to automatically determine how
    many 4x5 grids to scan.
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

    ocr_info = initialize_ocr()

    if show_progress and Console is not None:
        console = Console()
        with console.status("Waiting for Arc Raiders window…", spinner="dots"):
            window = wait_for_target_window(timeout=window_timeout)
    else:
        print("waiting for Arc Raiders to be active window...", flush=True)
        window = wait_for_target_window(timeout=window_timeout)
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

    ui: Optional[_ScanLiveUI] = None
    ui_running = False

    def _queue_event(message: str, style: str = "dim") -> None:
        if ui is not None and ui_running:
            ui.add_event(message, style=style)
        else:
            startup_events.append((message, style))

    def _detect_grid() -> Grid:
        """
        Move the cursor out of the grid, capture the ROI, and detect cells.
        """
        move_absolute(
            safe_point_abs[0],
            safe_point_abs[1],
        )
        pause_action()
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

    abort_if_escape_pressed()

    if show_progress:
        try:
            ui = _ScanLiveUI()
            ui.start()
            ui_running = True
        except Exception:
            ui = None
            ui_running = False

    if ui is not None and ui_running:
        ui.mode_label = "Dry run" if not apply_actions else "Scan"

        if stash_items is None and stash_count_text:
            ui.stash_label = f"? items (OCR '{stash_count_text}')"
        else:
            ui.stash_label = f"{items_label} items"

        ui.pages_label = f"{pages_to_scan} ({pages_source})"
        ui.set_total(items_total)
        ui.set_phase("Scanning…")
        ui.start_timer()

        for message, style in startup_events:
            ui.add_event(message, style=style)
        startup_events.clear()
    else:
        for message, _style in startup_events:
            print(f"[warning] {message}", flush=True)
        startup_events.clear()

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
                _queue_event(
                    f"Detected 2 consecutive empty slots at idx={first_empty_idx:03d},{empty_idx:03d} "
                    f"(page {detected_page + 1}/{pages_to_scan}, cell {detected_cell})",
                    style="yellow",
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
                    _queue_event(
                        f"Reached empty slot idx={stop_at_global_idx:03d}; stopping scan.",
                        style="yellow",
                    )
                    if ui is not None and ui_running:
                        ui.set_phase("Stopping…")
                    stop_scan = True
                    break

                abort_if_escape_pressed()
                if hasattr(window, "isAlive") and not window.isAlive:  # type: ignore[attr-defined]
                    raise RuntimeError("Target window closed during scan")

                sleep_with_abort(MENU_APPEAR_DELAY)
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
                    sleep_with_abort(INFOBOX_RETRY_DELAY)
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

                if ui is not None and ui_running:
                    processed = len(results)
                    total_label = str(items_total) if items_total is not None else "?"
                    current_label = (
                        f"{processed}/{total_label} • p{page + 1}/{pages_to_scan} "
                        f"r{cell.row}c{cell.col}"
                    )
                    ui.update_item(current_label, item_label, action_label)

                destructive_action = action_taken in {"SELL", "RECYCLE"}
                if destructive_action:
                    # Item removed; the next item collapses into this slot. Re-open the same cell.
                    open_cell_menu(cell, win_left, win_top)
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
                        if ui is not None and ui_running:
                            ui.set_phase("Stopping…")
                        stop_scan = True
                        break
                    open_cell_menu(cells[idx_in_page], win_left, win_top)

            if stop_scan:
                break
    finally:
        if ui is not None and ui_running:
            ui.stop()
            ui_running = False

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
    move_absolute(safe_point_abs[0], safe_point_abs[1])
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
# Live scan UI
# ---------------------------------------------------------------------------

AUTOSCRAPPER_ASCII = r"""
    ___       __       ____
  / _ |__ __/ /____  / __/__________ ____  ___  ___ ____
 / __ / // / __/ _ \_\ \/ __/ __/ _ `/ _ \/ _ \/ -_) __/
/_/ |_\_,_/\__/\___/___/\__/_/  \_,_/ .__/ .__/\__/_/
                                   /_/  /_/
""".strip(
    "\n"
)


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    if seconds < 0:
        seconds = 0
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


if (
    ProgressColumn is not None and Task is not None and Text is not None
):  # pragma: no cover

    class _ItemsPerSecondColumn(ProgressColumn):
        def render(self, task: Task) -> Text:
            speed = getattr(task, "finished_speed", None) or task.speed
            if speed is None:
                return Text("-- it/s", style="dim")
            return Text(f"{speed:0.2f} it/s", style="dim")

else:  # pragma: no cover - rich missing
    _ItemsPerSecondColumn = None  # type: ignore[assignment]


class _ScanLiveUI:
    def __init__(self) -> None:
        if (
            Console is None
            or Group is None
            or Live is None
            or Panel is None
            or Progress is None
            or BarColumn is None
            or SpinnerColumn is None
            or TextColumn is None
            or TaskProgressColumn is None
            or TimeElapsedColumn is None
            or TimeRemainingColumn is None
            or Align is None
            or Table is None
            or Text is None
            or box is None
        ):
            raise RuntimeError("Rich is required for the live scan UI.")

        self.console: Console = Console()
        self._events: deque[tuple[Text, Text]] = deque(maxlen=6)
        self._counts: Counter = Counter()

        self.phase = "Starting…"
        self.mode_label = "Scan"
        self.stash_label = ""
        self.pages_label = ""
        self.current_label = ""
        self.last_item_label = ""
        self.last_outcome_label = ""

        self._scan_started_at: Optional[float] = None

        self.progress: Progress = Progress(
            SpinnerColumn(style="cyan"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}", style="cyan"),
            TaskProgressColumn(),
            _ItemsPerSecondColumn() if _ItemsPerSecondColumn is not None else Text(""),
            TextColumn("[dim]elapsed[/]"),
            TimeElapsedColumn(),
            TextColumn("[dim]left[/]"),
            TimeRemainingColumn(),
            expand=True,
        )
        self._task_id = self.progress.add_task("Scanning", total=None, start=True)

        self._live: Live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )

    def start(self) -> None:
        self._live.start()

    def stop(self) -> None:
        self._live.stop()

    def start_timer(self) -> None:
        if self._scan_started_at is None:
            self._scan_started_at = time.perf_counter()

    def set_total(self, total: Optional[int]) -> None:
        self.progress.update(self._task_id, total=total)
        self.refresh()

    def set_phase(self, phase: str) -> None:
        self.phase = phase
        self.refresh()

    def add_event(self, message: str, style: str = "dim") -> None:
        timestamp = Text(time.strftime("%H:%M:%S"), style="dim")
        line = Text("• ", style="dim")
        line.append(message, style=style)
        self._events.append((timestamp, line))
        self.refresh()

    def update_item(self, current_label: str, item_label: str, outcome: str) -> None:
        self.progress.advance(self._task_id, 1)
        self._counts[outcome] += 1
        self.current_label = current_label
        self.last_item_label = item_label
        self.last_outcome_label = outcome
        self.refresh()

    def refresh(self) -> None:
        self._live.update(self._render(), refresh=True)

    def _render_counts(self) -> "Table":
        table = Table(
            box=box.SIMPLE,
            show_header=False,
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Outcome", justify="left", style="cyan", no_wrap=True)
        table.add_column("Count", justify="right", style="white", no_wrap=True)

        ordered = [
            "KEEP",
            "CRAFTING MATERIAL",
            "RECYCLE",
            "SELL",
            "DRY-RECYCLE",
            "DRY-SELL",
            "UNREADABLE",
            "SKIP",
        ]
        for key in ordered:
            if key not in self._counts:
                continue
            label = Text(key, style=_outcome_style(key))
            table.add_row(label, str(self._counts[key]))

        remaining = sorted(set(self._counts.keys()) - set(ordered))
        for key in remaining:
            label = Text(key, style=_outcome_style(key))
            table.add_row(label, str(self._counts[key]))

        return table

    def _completion_eta_label(self) -> str:
        task = self.progress.tasks[0]
        if task.total is None:
            return "--:--"

        speed = getattr(task, "finished_speed", None) or task.speed
        if speed is None or speed <= 0:
            return "--:--"

        remaining = max(0.0, float(task.total) - float(task.completed))
        seconds = remaining / speed
        eta = datetime.now() + timedelta(seconds=seconds)
        return eta.strftime("%H:%M:%S")

    def _render_events(self) -> "Table":
        table = Table.grid(expand=True)
        table.add_column(justify="right", width=8, no_wrap=True, style="dim")
        table.add_column(ratio=1, overflow="fold")

        if not self._events:
            table.add_row(Text("--:--:--", style="dim"), Text("—", style="dim"))
            return table

        for timestamp, line in self._events:
            table.add_row(timestamp, line)

        return table

    def _render(self) -> "Group":
        banner = Text(AUTOSCRAPPER_ASCII, style="bold cyan")

        subtitle = Text()
        if self.mode_label:
            subtitle.append(self.mode_label, style="dim")
            subtitle.append(" • ", style="dim")
        subtitle.append(self.phase, style="cyan")

        header = Group(
            Align.center(banner),
            Align.center(subtitle),
        )

        header_panel = Panel(
            header,
            box=box.ROUNDED,
            padding=(0, 1),
        )

        stats = Table.grid(expand=True)
        stats.add_column(ratio=1)
        stats.add_column(ratio=1)

        left = Table.grid(padding=(0, 1))
        left.add_column("k", style="cyan", justify="right", no_wrap=True)
        left.add_column("v", style="white", justify="left")
        if self.stash_label:
            left.add_row("Stash", self.stash_label)
        if self.pages_label:
            left.add_row("Pages", self.pages_label)
        if self._scan_started_at is not None:
            elapsed = time.perf_counter() - self._scan_started_at
            left.add_row("Elapsed", _format_duration(elapsed))
            left.add_row("Completion ETA", self._completion_eta_label())

        right = Table.grid(padding=(0, 1))
        right.add_column("k", style="cyan", justify="right", no_wrap=True)
        right.add_column("v", style="white", justify="left")
        if self.current_label:
            right.add_row("Current", self.current_label)
        if self.last_item_label:
            right.add_row("Last", self.last_item_label)
        if self.last_outcome_label:
            right.add_row(
                "Outcome",
                Text(
                    self.last_outcome_label,
                    style=_outcome_style(self.last_outcome_label),
                ),
            )

        stats.add_row(
            Panel(left, box=box.SIMPLE, title="Status", padding=(0, 1)),
            Panel(right, box=box.SIMPLE, title="Last Item", padding=(0, 1)),
        )

        counts_panel = Panel(
            self._render_counts(),
            box=box.SIMPLE,
            title="Outcomes",
            padding=(0, 1),
        )
        events_panel = Panel(
            self._render_events(),
            box=box.SIMPLE,
            title="Events",
            padding=(0, 1),
        )

        bottom = Table.grid(expand=True)
        bottom.add_column(ratio=1)
        bottom.add_column(ratio=2)
        bottom.add_row(counts_panel, events_panel)

        return Group(
            header_panel,
            stats,
            self.progress,
            bottom,
        )


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
    table.add_row("4x5 pages run", pages_value)
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
        help="Override auto-detected page count; number of 4x5 grids to scan.",
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
