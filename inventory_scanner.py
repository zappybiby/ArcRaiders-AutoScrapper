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

try:
    from tqdm.auto import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None

from grid_navigation import Cell, Grid
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
    scroll_to_next_grid,
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


# ---------------------------------------------------------------------------
# Navigation + scanning
# ---------------------------------------------------------------------------

def _progress(seq: Iterable[Cell], enabled: bool, total: int) -> Iterable[Cell]:
    """
    Wrap an iterable with tqdm when available and enabled.
    """
    if enabled and tqdm is not None:
        return tqdm(seq, total=total, desc="Scanning grid")
    return seq


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
    """
    if pages < 1:
        raise ValueError("pages must be >= 1")

    print("waiting for Arc Raiders to be active window...", flush=True)
    window = wait_for_target_window(timeout=window_timeout)
    win_left, win_top, win_width, win_height = window_rect(window)

    actions: ActionMap = {}
    if apply_actions:
        actions = actions_override if actions_override is not None else load_item_actions(actions_path)

    grid = Grid()
    cells = list(grid)
    cells_per_page = len(cells)
    total_cells = cells_per_page * pages
    page_cells = [(page, cell) for page in range(pages) for cell in cells]
    results: List[ItemActionResult] = []

    abort_if_escape_pressed()

    if not cells:
        return results

    progress = tqdm(total=total_cells, desc="Scanning grid") if show_progress and tqdm is not None else None
    current_page = -1
    idx = 0
    stop_at_global_idx: Optional[int] = None

    try:
        while idx < len(page_cells):
            page, cell = page_cells[idx]
            global_idx = page * cells_per_page + cell.index

            if page != current_page:
        if current_page != -1:
            scroll_to_next_grid(scroll_clicks_per_page)
        # TODO: Re-enable empty-cell detection once the heuristic is fixed.
        # empty_idx = _detect_first_empty_cell(
        #     page,
        #     cells,
        #     win_left,
        #     win_top,
        #     win_width,
        #     win_height,
        # )
        # if empty_idx is not None and (stop_at_global_idx is None or empty_idx < stop_at_global_idx):
        #     stop_at_global_idx = empty_idx
        #     detected_page = empty_idx // cells_per_page
        #     detected_cell = empty_idx % cells_per_page
        #     print(
        #         f"[empty] empty cell detected at idx={empty_idx:03d} "
        #         f"page={detected_page + 1:02d} cell={detected_cell:02d}"
        #     )
        # if stop_at_global_idx is not None and global_idx >= stop_at_global_idx:
        #     print(f"[empty] reached empty cell idx={stop_at_global_idx:03d}; stopping scan.")
        #     break
        open_cell_menu(cell, win_left, win_top)
        current_page = page

            if stop_at_global_idx is not None and global_idx >= stop_at_global_idx:
                print(f"[empty] reached empty cell idx={stop_at_global_idx:03d}; stopping scan.")
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
            action_taken = "SCAN_ONLY" if not apply_actions else ("SKIP_NO_ACTION_MAP" if not actions else "SKIP_UNLISTED")

            if apply_actions:
                if actions and item_name:
                    decision, decision_note = choose_decision(item_name, actions)
                    if decision is None:
                        action_taken = "SKIP_UNLISTED"
                    elif decision in {"KEEP", "CRAFTING MATERIAL"}:
                        action_taken = decision
                    elif decision == "SELL":
                        if infobox_rect is not None and infobox_crop is not None:
                            sell_bbox_rel, _ = find_action_bbox_by_ocr(infobox_crop, "sell")
                            if sell_bbox_rel is None:
                                action_taken = "SKIP_NO_ACTION_BBOX"
                            else:
                                _perform_sell(infobox_rect, sell_bbox_rel, win_left, win_top, win_width, win_height)
                                action_taken = "SELL"
                        else:
                            action_taken = "SKIP_NO_INFOBOX"
                    elif decision == "RECYCLE":
                        if infobox_rect is not None and infobox_crop is not None:
                            recycle_bbox_rel, _ = find_action_bbox_by_ocr(infobox_crop, "recycle")
                            if recycle_bbox_rel is None:
                                action_taken = "SKIP_NO_ACTION_BBOX"
                            else:
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
                            action_taken = "SKIP_NO_INFOBOX"
                elif not item_name:
                    action_taken = "SKIP_NO_NAME"
                elif not actions:
                    action_taken = "SKIP_NO_ACTION_MAP"
            elif not item_name:
                action_taken = "SKIP_NO_NAME"

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
                open_cell_menu(cell, win_left, win_top)
                continue

            if progress:
                progress.update(1)

            idx += 1
            if idx < len(page_cells):
                next_page, next_cell = page_cells[idx]
                next_global_idx = next_page * cells_per_page + next_cell.index
                if next_page == page and (stop_at_global_idx is None or next_global_idx < stop_at_global_idx):
                    open_cell_menu(next_cell, win_left, win_top)
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
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> Optional[int]:
    """
    Capture the current page and return the global index of the first empty cell.
    """
    abort_if_escape_pressed()

    # Keep the cursor out of the grid so it doesn't occlude cells.
    move_absolute(window_left + 10, window_top + 10, label="clear for empty detection")
    pause_action()

    window_bgr = capture_region((window_left, window_top, window_width, window_height))

    for cell in cells:
        abort_if_escape_pressed()
        x, y, w, h = cell.rect
        slot_bgr = window_bgr[y:y + h, x:x + w]
        if slot_bgr.size == 0:
            continue
        if is_slot_empty(slot_bgr):
            return page * len(cells) + cell.index

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
        help="Scroll clicks to reach the next grid (positive scrolls downward).",
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
        help="Scan only; do not click sell/recycle actions.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
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

    cells_per_page = len(Grid())
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
