from __future__ import annotations

import time
from dataclasses import dataclass, field
from itertools import cycle
from typing import Any, Iterable, Iterator, List, Optional, Tuple

from .actions import ActionExecutionContext, resolve_action_taken
from .outcomes import _describe_action
from .progress import ScanProgress
from ..core.item_actions import ActionMap, Decision, ItemActionResult, choose_decision
from ..interaction.inventory_grid import Cell, Grid
from ..interaction.ui_windows import (
    SCROLL_CLICKS_PATTERN,
    abort_if_escape_pressed,
    capture_region,
    move_absolute,
    open_cell_item_infobox,
    pause_action,
    scroll_to_next_grid_at,
    sleep_with_abort,
)
from ..ocr.inventory_vision import (
    InfoboxOcrResult,
    find_context_menu_crop,
    find_infobox,
    is_slot_empty,
    ocr_context_menu,
    ocr_infobox,
    reset_ocr_caches,
)


@dataclass(frozen=True)
class TimingConfig:
    input_action_delay: float
    cell_infobox_left_right_click_gap: float
    item_infobox_settle_delay: float
    infobox_retry_interval: float
    post_sell_recycle_delay: float
    ocr_retry_interval: float


@dataclass(frozen=True)
class ScanContext:
    window: Optional[Any]
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
    timing: TimingConfig


@dataclass(frozen=True)
class _InfoboxCaptureResult:
    infobox_rect: Optional[Tuple[int, int, int, int]]
    window_bgr: Optional[Any]
    capture_time: float
    find_time: float
    capture_attempts: int
    found_on_attempt: int
    context_menu_fallback: bool = False


@dataclass(frozen=True)
class _InfoboxReadResult:
    infobox_ocr: Optional[InfoboxOcrResult]
    infobox_bgr: Optional[Any]
    item_name: str
    raw_item_text: str
    preprocess_time: float
    ocr_time: float


@dataclass(frozen=True)
class _CellScanResult:
    result: ItemActionResult
    action_label: str
    item_label: str
    action_taken: str


@dataclass
class ScanRunState:
    results: List[ItemActionResult] = field(default_factory=list)
    pages_scanned: int = 0
    stop_at_global_idx: Optional[int] = None


@dataclass(frozen=True)
class _ScanLoopConfig:
    pages_to_scan: int
    infobox_retries: int
    ocr_unreadable_retries: int
    profile_timing: bool
    items_total: Optional[int]


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


def _scroll_clicks_sequence(click_pattern: Iterable[int]) -> Iterator[int]:
    """
    Yield repeating calibrated scroll counts.
    """
    pattern = tuple(int(clicks) for clicks in click_pattern)
    if not pattern:
        raise ValueError("scroll click pattern must not be empty")
    if any(clicks <= 0 for clicks in pattern):
        raise ValueError("scroll click pattern values must be > 0")
    return cycle(pattern)


def detect_grid(
    context: ScanContext,
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
    pause_action(context.timing.input_action_delay, stop_key=context.stop_key)
    roi_left = context.win_left + context.grid_roi[0]
    roi_top = context.win_top + context.grid_roi[1]
    inv_bgr = capture_region((roi_left, roi_top, context.grid_roi[2], context.grid_roi[3]))
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


class _ScanRunner:
    def __init__(
        self,
        *,
        context: ScanContext,
        initial_cells: List[Cell],
        scroll_sequence: Iterable[int],
        config: _ScanLoopConfig,
        progress_impl: Optional[ScanProgress],
        startup_events: List[Tuple[str, str]],
    ) -> None:
        self.context = context
        self.initial_cells = initial_cells
        self.scroll_sequence = scroll_sequence
        self.config = config
        self.progress_impl = progress_impl
        self.startup_events = startup_events
        self.state = ScanRunState()
        self._last_click_window_pos: Optional[Tuple[int, int]] = None
        # Tracks which UI detection method works for this scan session.
        # Set on the first successful detection, then reused for all
        # subsequent cells to avoid repeatedly trying the method that fails.
        self._detected_ui_mode: Optional[str] = None  # "context_menu" or "infobox"
        self.action_context = ActionExecutionContext(
            apply_actions=context.apply_actions,
            win_left=context.win_left,
            win_top=context.win_top,
            win_width=context.win_width,
            win_height=context.win_height,
            stop_key=context.stop_key,
            action_delay=context.timing.input_action_delay,
            item_infobox_settle_delay=context.timing.item_infobox_settle_delay,
            post_action_delay=context.timing.post_sell_recycle_delay,
        )

    def run(self) -> ScanRunState:
        for page in range(self.config.pages_to_scan):
            page_base_idx = page * self.context.cells_per_page
            if self.state.stop_at_global_idx is not None and page_base_idx >= self.state.stop_at_global_idx:
                break
            self._scan_single_page(page)

        return self.state

    def _emit_event(self, message: str, *, style: str = "dim") -> None:
        _queue_event(
            self.progress_impl,
            self.startup_events,
            message,
            style=style,
        )

    def _should_stop_at_index(self, global_idx: int) -> bool:
        stop_at_global_idx = self.state.stop_at_global_idx
        if stop_at_global_idx is None or global_idx < stop_at_global_idx:
            return False

        self._emit_event(
            f"Reached empty slot idx={stop_at_global_idx:03d}; stopping scan.",
            style="yellow",
        )
        if self.progress_impl is not None:
            self.progress_impl.set_phase("Stopping…")
        return True

    def _open_cell_infobox(self, cell: Cell) -> None:
        cx, cy, cw, ch = cell.safe_rect
        self._last_click_window_pos = (cx + cw // 2, cy + ch // 2)
        open_cell_item_infobox(
            cell,
            self.context.win_left,
            self.context.win_top,
            stop_key=self.context.stop_key,
            pause=self.context.timing.input_action_delay,
            left_right_click_gap=self.context.timing.cell_infobox_left_right_click_gap,
        )

    def _capture_window(self) -> Tuple[Any, float]:
        capture_start = time.perf_counter()
        window_bgr = capture_region(
            (
                self.context.win_left,
                self.context.win_top,
                self.context.win_width,
                self.context.win_height,
            )
        )
        return window_bgr, time.perf_counter() - capture_start

    def _try_context_menu_crop(self, window_bgr: Any) -> Optional[Tuple[int, int, int, int]]:
        if self._last_click_window_pos is None:
            return None
        cx, cy = self._last_click_window_pos
        return find_context_menu_crop(window_bgr, cx, cy)

    def _try_infobox_color_detection(self, window_bgr: Any) -> Tuple[Optional[Tuple[int, int, int, int]], float]:
        find_start = time.perf_counter()
        rect = find_infobox(window_bgr)
        return rect, time.perf_counter() - find_start

    def _capture_infobox_with_retries(self) -> _InfoboxCaptureResult:
        infobox_rect: Optional[Tuple[int, int, int, int]] = None
        window_bgr = None
        capture_time = 0.0
        find_time = 0.0
        capture_attempts = 0
        found_on_attempt = 0
        context_menu_fallback = False

        # Fast path: if a previous cell already determined the UI mode,
        # skip the method that is known to fail for this session.
        skip_infobox = self._detected_ui_mode == "context_menu"
        skip_context_menu = self._detected_ui_mode == "infobox"

        # --- Attempt 1: context-menu positional crop (near-free) ---
        if not skip_context_menu and self._last_click_window_pos is not None:
            window_bgr, cap_t = self._capture_window()
            capture_time += cap_t
            capture_attempts += 1

            infobox_rect = self._try_context_menu_crop(window_bgr)
            if infobox_rect is not None:
                found_on_attempt = 1
                context_menu_fallback = True
                if self._detected_ui_mode is None:
                    self._detected_ui_mode = "context_menu"
                return _InfoboxCaptureResult(
                    infobox_rect=infobox_rect,
                    window_bgr=window_bgr,
                    capture_time=capture_time,
                    find_time=find_time,
                    capture_attempts=capture_attempts,
                    found_on_attempt=found_on_attempt,
                    context_menu_fallback=True,
                )

        # --- Attempt 2: color-based infobox detection with retries ---
        # Only run when infobox mode is active or no mode has been
        # established yet.  When context-menu mode is established
        # (skip_infobox=True) but the crop returned nothing, the menu
        # simply was not visible for this cell (e.g. empty slot or
        # timing issue).  Falling through to infobox color detection
        # adds multiple capture+sleep cycles with zero benefit because
        # the game's current dark UI never matches the legacy
        # INFOBOX_COLOR_BGR cream color.
        if not skip_infobox:
            for attempt in range(1, self.config.infobox_retries + 1):
                capture_attempts += 1
                abort_if_escape_pressed(self.context.stop_key)

                if window_bgr is None or attempt > 1:
                    window_bgr, cap_t = self._capture_window()
                    capture_time += cap_t

                rect, ft = self._try_infobox_color_detection(window_bgr)
                find_time += ft

                if rect is not None:
                    infobox_rect = rect
                    found_on_attempt = capture_attempts
                    if self._detected_ui_mode is None:
                        self._detected_ui_mode = "infobox"
                    break

                if attempt < self.config.infobox_retries:
                    sleep_with_abort(
                        self.context.timing.infobox_retry_interval,
                        stop_key=self.context.stop_key,
                    )
                    pause_action(
                        self.context.timing.input_action_delay,
                        stop_key=self.context.stop_key,
                    )

        # --- Fallback: if color detection failed, try context menu crop
        # (only if we haven't tried it above) ---
        if (
            infobox_rect is None
            and not context_menu_fallback
            and window_bgr is not None
            and self._last_click_window_pos is not None
        ):
            infobox_rect = self._try_context_menu_crop(window_bgr)
            if infobox_rect is not None:
                found_on_attempt = capture_attempts
                context_menu_fallback = True
                if self._detected_ui_mode is None:
                    self._detected_ui_mode = "context_menu"

        return _InfoboxCaptureResult(
            infobox_rect=infobox_rect,
            window_bgr=window_bgr,
            capture_time=capture_time,
            find_time=find_time,
            capture_attempts=capture_attempts,
            found_on_attempt=found_on_attempt,
            context_menu_fallback=context_menu_fallback,
        )

    def _ocr_infobox_with_retries(
        self,
        capture_result: _InfoboxCaptureResult,
    ) -> _InfoboxReadResult:
        infobox_rect = capture_result.infobox_rect
        window_bgr = capture_result.window_bgr

        infobox_ocr: Optional[InfoboxOcrResult] = None
        infobox_bgr: Optional[Any] = None
        item_name = ""
        raw_item_text = ""
        preprocess_time = 0.0
        ocr_time = 0.0

        if infobox_rect is None or window_bgr is None:
            return _InfoboxReadResult(
                infobox_ocr=infobox_ocr,
                infobox_bgr=infobox_bgr,
                item_name=item_name,
                raw_item_text=raw_item_text,
                preprocess_time=preprocess_time,
                ocr_time=ocr_time,
            )

        pause_action(
            self.context.timing.input_action_delay,
            stop_key=self.context.stop_key,
        )
        x, y, w, h = infobox_rect

        for ocr_attempt in range(self.config.ocr_unreadable_retries + 1):
            if ocr_attempt > 0:
                sleep_with_abort(
                    self.context.timing.ocr_retry_interval,
                    stop_key=self.context.stop_key,
                )
                try:
                    infobox_bgr = capture_region((self.context.win_left + x, self.context.win_top + y, w, h))
                except Exception:
                    window_bgr = capture_region(
                        (
                            self.context.win_left,
                            self.context.win_top,
                            self.context.win_width,
                            self.context.win_height,
                        )
                    )
                    infobox_bgr = window_bgr[y : y + h, x : x + w]
            else:
                infobox_bgr = window_bgr[y : y + h, x : x + w]

            infobox_ocr = (
                ocr_context_menu(infobox_bgr) if capture_result.context_menu_fallback else ocr_infobox(infobox_bgr)
            )
            preprocess_time += infobox_ocr.preprocess_time
            ocr_time += infobox_ocr.ocr_time
            item_name = infobox_ocr.item_name
            raw_item_text = infobox_ocr.raw_item_text
            if item_name:
                break

        return _InfoboxReadResult(
            infobox_ocr=infobox_ocr,
            infobox_bgr=infobox_bgr,
            item_name=item_name,
            raw_item_text=raw_item_text,
            preprocess_time=preprocess_time,
            ocr_time=ocr_time,
        )

    def _process_cell(self, *, page: int, cell: Cell) -> _CellScanResult:
        global_idx = page * self.context.cells_per_page + cell.index
        cell_start = time.perf_counter()

        abort_if_escape_pressed(self.context.stop_key)
        window = self.context.window
        if window is not None and hasattr(window, "isAlive"):
            try:
                if not window.isAlive:  # type: ignore[attr-defined]
                    raise RuntimeError("Target window closed during scan")
            except RuntimeError:
                raise
            except Exception:
                raise RuntimeError("Target window closed during scan (handle stale)")

        sleep_with_abort(
            self.context.timing.item_infobox_settle_delay,
            stop_key=self.context.stop_key,
        )
        pause_action(
            self.context.timing.input_action_delay,
            stop_key=self.context.stop_key,
        )

        capture_result = self._capture_infobox_with_retries()
        ocr_result = self._ocr_infobox_with_retries(capture_result)

        decision: Optional[Decision] = None
        decision_note: Optional[str] = None
        if self.context.actions and ocr_result.item_name:
            decision, decision_note = choose_decision(
                ocr_result.item_name,
                self.context.actions,
            )

        action_taken = resolve_action_taken(
            decision=decision,
            item_name=ocr_result.item_name,
            actions=self.context.actions,
            infobox_rect=capture_result.infobox_rect,
            infobox_bgr=ocr_result.infobox_bgr,
            infobox_ocr=ocr_result.infobox_ocr,
            context=self.action_context,
        )

        action_label, _details = _describe_action(action_taken)
        item_label = (ocr_result.item_name or ocr_result.raw_item_text or "<unreadable>").replace("\n", " ").strip()

        result = ItemActionResult(
            page=page,
            cell=cell,
            item_name=ocr_result.item_name,
            decision=decision,
            action_taken=action_taken,
            raw_item_text=ocr_result.raw_item_text or None,
            note=decision_note,
        )

        if self.config.profile_timing:
            total_time = time.perf_counter() - cell_start
            self._emit_event(
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
        self,
        *,
        page: int,
        cell: Cell,
        cell_scan: _CellScanResult,
    ) -> None:
        self.state.results.append(cell_scan.result)
        if self.progress_impl is None:
            return

        processed = len(self.state.results)
        total_label = str(self.config.items_total) if self.config.items_total is not None else "?"
        current_label = f"{processed}/{total_label} • p{page + 1}/{self.config.pages_to_scan} r{cell.row}c{cell.col}"
        self.progress_impl.update_item(
            current_label,
            cell_scan.item_label,
            cell_scan.action_label,
        )

    def _update_stop_from_empty_detection(self, *, page: int, cells: List[Cell]) -> None:
        empty_idx = _detect_consecutive_empty_stop_idx(
            page,
            cells,
            self.context.cells_per_page,
            self.context.win_left,
            self.context.win_top,
            self.context.win_width,
            self.context.win_height,
            self.context.safe_point_abs,
            self.context.stop_key,
            self.context.timing.input_action_delay,
        )
        if empty_idx is None:
            return
        if self.state.stop_at_global_idx is not None and empty_idx >= self.state.stop_at_global_idx:
            return

        self.state.stop_at_global_idx = empty_idx
        first_empty_idx = max(0, empty_idx - 1)
        detected_page = empty_idx // self.context.cells_per_page
        detected_cell = empty_idx % self.context.cells_per_page
        self._emit_event(
            f"Detected 2 consecutive empty slots at idx={first_empty_idx:03d},{empty_idx:03d} "
            f"(page {detected_page + 1}/{self.config.pages_to_scan}, cell {detected_cell})",
            style="yellow",
        )

    def _scan_cells_on_page(self, *, page: int, cells: List[Cell]) -> None:
        if not cells:
            return

        max_destructive_retries = 5
        idx_in_page = 0
        destructive_retries = 0
        self._open_cell_infobox(cells[0])

        while idx_in_page < len(cells):
            cell = cells[idx_in_page]
            global_idx = page * self.context.cells_per_page + cell.index

            if self._should_stop_at_index(global_idx):
                break

            cell_scan = self._process_cell(page=page, cell=cell)
            self._record_processed_cell(page=page, cell=cell, cell_scan=cell_scan)

            destructive_action = cell_scan.action_taken in {"SELL", "RECYCLE"}
            if destructive_action:
                destructive_retries += 1
                if destructive_retries > max_destructive_retries:
                    self._emit_event(
                        f"Exceeded {max_destructive_retries} destructive retries at "
                        f"idx={global_idx:03d}; advancing to next cell.",
                        style="yellow",
                    )
                    destructive_retries = 0
                    idx_in_page += 1
                    if idx_in_page < len(cells):
                        self._open_cell_infobox(cells[idx_in_page])
                    continue
                # Item removed; the next item collapses into this slot. Re-open the same cell.
                self._open_cell_infobox(cell)
                continue

            destructive_retries = 0
            idx_in_page += 1
            if idx_in_page < len(cells):
                next_global_idx = page * self.context.cells_per_page + cells[idx_in_page].index
                if self._should_stop_at_index(next_global_idx):
                    break
                self._open_cell_infobox(cells[idx_in_page])

    def _scan_single_page(self, page: int) -> None:
        self.state.pages_scanned += 1
        # Allow re-detection of UI mode each page in case the game UI changed.
        if page > 0:
            self._detected_ui_mode = None

        cells = self.initial_cells
        if page > 0:
            clicks = next(self.scroll_sequence)
            scroll_to_next_grid_at(
                clicks,
                self.context.grid_center_abs,
                self.context.safe_point_abs,
                stop_key=self.context.stop_key,
                pause=self.context.timing.input_action_delay,
            )
            grid = detect_grid(self.context, self.progress_impl, self.startup_events)
            cells = list(grid)

        self._update_stop_from_empty_detection(page=page, cells=cells)
        self._scan_cells_on_page(page=page, cells=cells)


def scan_pages(
    *,
    context: ScanContext,
    initial_cells: List[Cell],
    pages_to_scan: int,
    infobox_retries: int,
    ocr_unreadable_retries: int,
    profile_timing: bool,
    progress_impl: Optional[ScanProgress],
    startup_events: List[Tuple[str, str]],
    items_total: Optional[int],
) -> ScanRunState:
    reset_ocr_caches()
    config = _ScanLoopConfig(
        pages_to_scan=pages_to_scan,
        infobox_retries=infobox_retries,
        ocr_unreadable_retries=ocr_unreadable_retries,
        profile_timing=profile_timing,
        items_total=items_total,
    )
    scroll_sequence = _scroll_clicks_sequence(SCROLL_CLICKS_PATTERN)
    runner = _ScanRunner(
        context=context,
        initial_cells=initial_cells,
        scroll_sequence=scroll_sequence,
        config=config,
        progress_impl=progress_impl,
        startup_events=startup_events,
    )
    return runner.run()
