"""
inventory_scanner.py

Scan the 4x6 inventory grid by hovering each cell, opening the context
menu, locating the light infobox (#f9eedf), and OCR-ing the item title.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from detect_tesseract import configure_pytesseract

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
    find_infobox,
    ocr_infobox,
    recycle_confirm_button_center,
    rect_center,
    sell_confirm_button_center,
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
    )
    click_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        label="sell",
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = sell_confirm_button_center(window_left, window_top, window_width, window_height)
    move_absolute(
        cx,
        cy,
        label="sell confirm",
    )
    click_absolute(cx, cy, label="sell confirm")


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
    )
    click_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        label="recycle",
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = recycle_confirm_button_center(window_left, window_top, window_width, window_height)
    move_absolute(
        cx,
        cy,
        label="recycle confirm",
    )
    click_absolute(cx, cy, label="recycle confirm")


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
    profile_timing: bool = False,
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
                cell_start = time.perf_counter()

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
                infobox_ocr = None
                sell_bbox_rel: Optional[Tuple[int, int, int, int]] = None
                recycle_bbox_rel: Optional[Tuple[int, int, int, int]] = None
                capture_time = 0.0
                ocr_time = 0.0
                preprocess_time = 0.0
                find_time = 0.0
                capture_attempts = 0
                found_on_attempt = 0

                for attempt in range(1, infobox_retries + 1):
                    capture_attempts += 1
                    abort_if_escape_pressed()
                    capture_start = time.perf_counter()
                    window_bgr = capture_region((win_left, win_top, win_width, win_height))
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
                    infobox_ocr = ocr_infobox(window_bgr[y:y + h, x:x + w])
                    preprocess_time += infobox_ocr.preprocess_time
                    ocr_time += infobox_ocr.ocr_time
                    item_name = infobox_ocr.item_name
                    sell_bbox_rel = infobox_ocr.sell_bbox
                    recycle_bbox_rel = infobox_ocr.recycle_bbox

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
                    if infobox_rect is not None and infobox_ocr is not None:
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
# Output formatting
# ---------------------------------------------------------------------------

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
        reason = _SKIP_REASONS.get(action_taken, action_taken.replace("SKIP_", "").replace("_", " ").lower())
        details.append(reason)
        return "SKIP", details

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
        "SKIP": "red",
    }.get(base, "white")


def _summarize_results(results: List[ItemActionResult]) -> Counter:
    summary = Counter()
    for result in results:
        label, _ = _describe_action(result.action_taken)
        summary[label] += 1
    return summary


def _render_summary(summary: Counter, console: Optional["Console"]) -> None:
    ordered_keys = [k for k in ("KEEP", "CRAFTING MATERIAL", "RECYCLE", "SELL") if k in summary]
    ordered_keys += [k for k in ("DRY-KEEP", "DRY-RECYCLE", "DRY-SELL") if k in summary]
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


def _render_results(results: List[ItemActionResult], cells_per_page: int) -> None:
    if not results:
        print("No results to display.")
        return

    console = Console() if Console is not None and Table is not None and Text is not None and box is not None else None
    summary = _summarize_results(results)

    if console is None:
        for result in results:
            label = result.item_name or "<unreadable>"
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
        label = result.item_name or "<unreadable>"
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
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Log per-item timing (capture, OCR, total) to identify bottlenecks.",
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
            profile_timing=args.profile,
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
    _render_results(results, cells_per_page)

    return 0


if __name__ == "__main__":
    sys.exit(main())
