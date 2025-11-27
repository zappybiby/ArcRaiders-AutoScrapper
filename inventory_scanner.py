"""
inventory_scanner.py

Scan the 4x6 inventory grid by hovering each cell, opening the context
menu, locating the light infobox (#f9eedf), and OCR-ing the item title.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from detect_tesseract import configure_pytesseract

try:
    from tqdm.auto import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None

from grid_navigation import (
    Cell,
    Grid,
    grid_center_point,
    inventory_roi_rect,
    safe_mouse_point,
)
from inventory_domain import (
    ActionMap,
    Decision,
    ItemActionResult,
    ITEM_ACTIONS_PATH,
    choose_decision,
    load_item_actions,
)
from ui_backend import (
    SELL_RECYCLE_ACTION_DELAY,
    SELL_RECYCLE_MOVE_DURATION,
    SCROLL_CLICKS_PER_PAGE,
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
    window_rect,
)
from vision_ocr import (
    find_action_bbox_by_ocr,
    find_infobox,
    ocr_item_name,
    recycle_confirm_button_center,
    rect_center,
    sell_confirm_button_center,
    title_roi,
    is_slot_empty,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MENU_APPEAR_DELAY = 0.05
INFOBOX_RETRY_DELAY = 0.05
INFOBOX_RETRIES = 3


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

    cx, cy = sell_confirm_button_center(window_left, window_top, window_width, window_height)
    move_absolute(
        cx,
        cy,
        label="sell confirm",
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, label="sell confirm", pause=SELL_RECYCLE_ACTION_DELAY)


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

    cx, cy = recycle_confirm_button_center(window_left, window_top, window_width, window_height)
    move_absolute(
        cx,
        cy,
        label="recycle confirm",
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, label="recycle confirm", pause=SELL_RECYCLE_ACTION_DELAY)


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
    show_progress: bool = True,
    pages: int = 1,
    scroll_clicks_per_page: int = SCROLL_CLICKS_PER_PAGE,
    apply_actions: bool = True,
    actions_path: Path = ITEM_ACTIONS_PATH,
    actions_override: Optional[ActionMap] = None,
) -> List[ItemActionResult]:
    """
    Walk each 6x4 grid (top-to-bottom, left-to-right), OCR each cell's item
    title, and apply the configured keep/recycle/sell decision when possible.
    Decisions come from items_actions.json unless an override map is provided.
    Cells are detected via contours inside a normalized ROI, and scrolling
    alternates between `scroll_clicks_per_page` and `scroll_clicks_per_page + 1`
    to handle the carousel offset.
    """
    if pages < 1:
        raise ValueError("pages must be >= 1")

    print("waiting for Arc Raiders to be active window...", flush=True)
    window = wait_for_target_window(timeout=window_timeout)
    win_left, win_top, win_width, win_height = window_rect(window)

    actions: ActionMap = actions_override if actions_override is not None else load_item_actions(actions_path)

    grid_roi = inventory_roi_rect(win_width, win_height)
    safe_point = safe_mouse_point(win_width, win_height)
    safe_point_abs = (win_left + safe_point[0], win_top + safe_point[1])
    grid_center = grid_center_point(win_width, win_height)
    grid_center_abs = (win_left + grid_center[0], win_top + grid_center[1])

    def _detect_grid() -> Grid:
        """
        Move the cursor out of the grid, capture the ROI, and detect cells.
        """
        move_absolute(safe_point_abs[0], safe_point_abs[1], label="move to safe area for detection")
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
    cells_per_page = Grid.COLS * Grid.ROWS
    total_cells = cells_per_page * pages
    results: List[ItemActionResult] = []

    abort_if_escape_pressed()

    progress = tqdm(total=total_cells, desc="Scanning grid") if show_progress and tqdm is not None else None
    stop_at_global_idx: Optional[int] = None
    scroll_sequence = _scroll_clicks_sequence(scroll_clicks_per_page)
    stop_scan = False

    try:
        for page in range(pages):
            if page > 0:
                clicks = next(scroll_sequence)
                scroll_to_next_grid_at(clicks, grid_center_abs, safe_point_abs)
                grid = _detect_grid()
                cells = list(grid)

            page_base_idx = page * cells_per_page
            if stop_at_global_idx is not None and page_base_idx >= stop_at_global_idx:
                break

            empty_idx = _detect_first_empty_cell(
                page,
                cells,
                cells_per_page,
                win_left,
                win_top,
                win_width,
                win_height,
                safe_point_abs,
            )
            if empty_idx is not None and (stop_at_global_idx is None or empty_idx < stop_at_global_idx):
                stop_at_global_idx = empty_idx
                detected_page = empty_idx // cells_per_page
                detected_cell = empty_idx % cells_per_page
                print(
                    f"[empty] empty cell detected at idx={empty_idx:03d} "
                    f"page={detected_page + 1:02d} cell={detected_cell:02d}"
                )

            if not cells:
                continue

            idx_in_page = 0
            open_cell_menu(cells[0], win_left, win_top)

            while idx_in_page < len(cells):
                cell = cells[idx_in_page]
                global_idx = page * cells_per_page + cell.index

                if stop_at_global_idx is not None and global_idx >= stop_at_global_idx:
                    print(f"[empty] reached empty cell idx={stop_at_global_idx:03d}; stopping scan.")
                    stop_scan = True
                    break

                abort_if_escape_pressed()
                if hasattr(window, "isAlive") and not window.isAlive:  # type: ignore[attr-defined]
                    raise RuntimeError("Target window closed during scan")

                time.sleep(MENU_APPEAR_DELAY)
                pause_action()

                infobox_rect: Optional[Tuple[int, int, int, int]] = None
                window_bgr = None

                for _ in range(infobox_retries):
                    abort_if_escape_pressed()
                    window_bgr = capture_region((win_left, win_top, win_width, win_height))
                    infobox_rect = find_infobox(window_bgr)
                    if infobox_rect:
                        break
                    time.sleep(INFOBOX_RETRY_DELAY)
                    pause_action()

                item_name = ""
                infobox_crop = None
                if infobox_rect and window_bgr is not None:
                    pause_action()
                    title_x, title_y, title_w, title_h = title_roi(infobox_rect)
                    title_crop = window_bgr[title_y:title_y + title_h, title_x:title_x + title_w]
                    item_name = ocr_item_name(title_crop)
                    x, y, w, h = infobox_rect
                    infobox_crop = window_bgr[y:y + h, x:x + w]

                decision: Optional[Decision] = None
                decision_note: Optional[str] = None
                action_taken = "SCAN_ONLY"

                if actions and item_name:
                    decision, decision_note = choose_decision(item_name, actions)

                if decision is None:
                    if not item_name:
                        action_taken = "SKIP_NO_NAME"
                    elif not actions:
                        action_taken = "SKIP_NO_ACTION_MAP"
                    else:
                        action_taken = "SKIP_UNLISTED"
                elif decision in {"KEEP", "CRAFTING MATERIAL"}:
                    action_taken = decision
                elif decision == "SELL":
                    if infobox_rect is not None and infobox_crop is not None:
                        sell_bbox_rel, _ = find_action_bbox_by_ocr(infobox_crop, "sell")
                        if sell_bbox_rel is None:
                            action_taken = "SKIP_NO_ACTION_BBOX"
                        elif apply_actions:
                            _perform_sell(infobox_rect, sell_bbox_rel, win_left, win_top, win_width, win_height)
                            action_taken = "SELL"
                        else:
                            action_taken = "DRY_RUN_SELL"
                    else:
                        action_taken = "SKIP_NO_INFOBOX"
                elif decision == "RECYCLE":
                    if infobox_rect is not None and infobox_crop is not None:
                        recycle_bbox_rel, _ = find_action_bbox_by_ocr(infobox_crop, "recycle")
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
                action_label = "SKIPPED" if action_taken.startswith("SKIP") else action_taken
                detail_suffix = f" detail={action_taken}" if action_label != action_taken else ""
                item_label = item_name or "<unreadable>"
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

                idx_in_page += 1
                if idx_in_page < len(cells):
                    next_global_idx = page * cells_per_page + cells[idx_in_page].index
                    if stop_at_global_idx is not None and next_global_idx >= stop_at_global_idx:
                        print(f"[empty] reached empty cell idx={stop_at_global_idx:03d}; stopping scan.")
                        stop_scan = True
                        break
                    open_cell_menu(cells[idx_in_page], win_left, win_top)

            if stop_scan:
                break
    finally:
        if progress:
            progress.close()

    return results


# ---------------------------------------------------------------------------
# Empty cell detection
# ---------------------------------------------------------------------------

def _detect_first_empty_cell(
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
    Capture the current page and return the global index of the first empty cell.
    """
    abort_if_escape_pressed()

    # Keep the cursor out of the grid so it doesn't occlude cells.
    move_absolute(safe_point_abs[0], safe_point_abs[1], label="clear for empty detection")
    pause_action()

    window_bgr = capture_region((window_left, window_top, window_width, window_height))

    for cell in cells:
        abort_if_escape_pressed()
        x, y, w, h = cell.safe_rect
        slot_bgr = window_bgr[y:y + h, x:x + w]
        if slot_bgr.size == 0:
            continue
        if is_slot_empty(slot_bgr):
            return page * cells_per_page + cell.index

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan the ARC Raiders inventory grid(s).")
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of 6x4 grids to scan by scrolling down between pages.",
    )
    parser.add_argument(
        "--scroll-clicks",
        type=int,
        default=SCROLL_CLICKS_PER_PAGE,
        help="Initial scroll clicks to reach the next grid (alternates with +1 on following page).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bar output.",
    )
    parser.add_argument(
        "--actions-file",
        type=Path,
        default=ITEM_ACTIONS_PATH,
        help="Path to items_actions.json for keep/recycle/sell decisions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only; log planned actions without clicking sell/recycle.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        tesseract_cmd = configure_pytesseract()
        print(f"[tesseract] using {tesseract_cmd}", flush=True)
        results = scan_inventory(
            show_progress=not args.no_progress,
            pages=args.pages,
            scroll_clicks_per_page=args.scroll_clicks,
            apply_actions=not args.dry_run,
            actions_path=args.actions_file,
        )
    except KeyboardInterrupt:
        print("Aborted by Escape key.")
        return 0
    except TimeoutError as exc:
        print(exc)
        return 1
    except RuntimeError as exc:
        print(f"Fatal: {exc}")
        return 1

    cells_per_page = Grid.COLS * Grid.ROWS
    for result in results:
        label = result.item_name or "<unreadable>"
        global_idx = result.page * cells_per_page + result.cell.index
        decision_label = result.decision or result.action_taken
        action_suffix = f" ({result.action_taken})" if result.action_taken != decision_label else ""
        note_suffix = f" {result.note}" if result.note else ""
        print(
            f"[page {result.page + 1:02d}] global_idx={global_idx:03d} "
            f"Cell r{result.cell.row} c{result.cell.col} idx={result.cell.index:02d}: "
            f"{label} -> {decision_label}{action_suffix}{note_suffix}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
