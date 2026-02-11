from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Deque, Optional, TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from ..config import load_scan_settings
from ..interaction.keybinds import stop_key_label
from ..interaction.ui_windows import (
    TARGET_APP,
    WINDOW_TIMEOUT,
    WindowSnapshot,
    build_window_snapshot,
    get_active_target_window,
    stop_key_pressed,
)
from ..scanner.outcomes import _describe_action, _outcome_style
from ..scanner.progress import ScanProgress
from ..scanner.types import ScanStats
from .common import AppScreen, MessageScreen

if TYPE_CHECKING:
    from ..core.item_actions import ItemActionResult


CELLS_PER_PAGE = 20
EVENT_LIMIT = 8


@dataclass(frozen=True)
class ScanUpdate:
    kind: str
    payload: dict


@dataclass
class ScanState:
    phase: str = "Starting..."
    mode_label: str = ""
    stash_label: str = ""
    pages_label: str = ""
    current_label: str = ""
    last_item_label: str = ""
    last_outcome_label: str = ""
    total: Optional[int] = None
    completed: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    events: Deque[Text] = field(default_factory=lambda: deque(maxlen=EVENT_LIMIT))
    start_time: Optional[float] = None


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


def _item_label(result: "ItemActionResult") -> str:
    return (
        (result.item_name or result.raw_item_text or "<unreadable>")
        .replace("\n", " ")
        .strip()
    )


def _com_error_details(exc: BaseException) -> Optional[tuple[int, str, str]]:
    args = getattr(exc, "args", ())
    if len(args) < 2 or not isinstance(args[0], int) or not isinstance(args[1], str):
        return None
    hresult = args[0]
    text = args[1]
    if hresult < 0:
        hresult_hex = f"0x{hresult & 0xFFFFFFFF:08X}"
    else:
        hresult_hex = f"0x{hresult:08X}"
    return hresult, text, hresult_hex


def _write_crash_report(content: str) -> Optional[str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path.cwd() / f"autoscrapper_crash_{timestamp}.log"
    try:
        path.write_text(content, encoding="utf-8")
    except Exception:
        return None
    return str(path)


def _format_exception_for_ui(exc: BaseException, *, context: str) -> str:
    trace = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    ).rstrip()
    lines = [context, "", f"{type(exc).__name__}: {exc}"]
    com_details = _com_error_details(exc)
    if com_details is not None:
        hresult, text, hresult_hex = com_details
        lines.append(f"COM error: {hresult_hex} ({text})")
    lines.extend(["", "Traceback:", trace])
    report_path = _write_crash_report("\n".join(lines))
    if report_path:
        lines.extend(["", f"Crash report: {report_path}"])
    return "\n".join(lines)


class TextualScanProgress(ScanProgress):
    def __init__(self, updates: "queue.Queue[ScanUpdate]") -> None:
        self._updates = updates

    def _emit(self, kind: str, **payload: object) -> None:
        self._updates.put(ScanUpdate(kind=kind, payload=payload))

    def start(self) -> None:
        self._emit("start")

    def stop(self) -> None:
        self._emit("stop")

    def set_total(self, total: Optional[int]) -> None:
        self._emit("total", total=total)

    def set_phase(self, phase: str) -> None:
        self._emit("phase", phase=phase)

    def set_mode(self, mode_label: str) -> None:
        self._emit("mode", mode_label=mode_label)

    def set_stash_label(self, stash_label: str) -> None:
        self._emit("stash", stash_label=stash_label)

    def set_pages_label(self, pages_label: str) -> None:
        self._emit("pages", pages_label=pages_label)

    def start_timer(self) -> None:
        self._emit("timer")

    def add_event(self, message: str, *, style: str = "dim") -> None:
        self._emit("event", message=message, style=style)

    def update_item(self, current_label: str, item_label: str, outcome: str) -> None:
        self._emit(
            "item",
            current_label=current_label,
            item_label=item_label,
            outcome=outcome,
        )


class ScanScreen(Screen):
    def __init__(self, *, dry_run: bool) -> None:
        super().__init__()
        self.dry_run = dry_run
        self._settings = load_scan_settings()
        self._state = ScanState()
        self._updates: "queue.Queue[ScanUpdate]" = queue.Queue()
        self._scan_complete = False
        self._scan_update_timer = None
        self._window_wait_timer = None
        self._window_wait_started: Optional[float] = None
        self._scan_started = False
        self._results: list["ItemActionResult"] = []
        self._stats: Optional[ScanStats] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="scan-layout"):
            title = "Scan (Dry Run)" if self.dry_run else "Scan"
            stop_label = stop_key_label(self._settings.stop_key)
            yield Static(title, classes="menu-title")
            yield Static(
                f"Alt-tab to ARC Raiders. Press {stop_label} in the game window to stop scanning.",
                classes="hint",
                id="scan-hint",
            )
            with Horizontal(id="scan-top"):
                yield Static(id="scan-status")
                yield Static(id="scan-last")
            yield Static(id="scan-progress")
            with Horizontal(id="scan-bottom"):
                yield Static(id="scan-counts")
                yield Static(id="scan-events")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_panels()
        self._scan_update_timer = self.set_interval(0.25, self._drain_updates)
        self._start_window_wait()

    def on_screen_resume(self, _event) -> None:  # type: ignore[override]
        if self._scan_complete:
            self.app.pop_screen()

    def _start_window_wait(self) -> None:
        self._window_wait_started = time.monotonic()
        self._updates.put(
            ScanUpdate(
                kind="phase", payload={"phase": "Waiting for Arc Raiders window…"}
            )
        )
        self._window_wait_timer = self.set_interval(0.25, self._poll_for_window)

    def _stop_window_wait(self) -> None:
        if self._window_wait_timer is not None:
            self._window_wait_timer.pause()

    def _poll_for_window(self) -> None:
        if self._scan_complete or self._scan_started:
            self._stop_window_wait()
            return
        if self._window_wait_started is None:
            self._window_wait_started = time.monotonic()

        if stop_key_pressed(self._settings.stop_key):
            self._stop_window_wait()
            self._updates.put(
                ScanUpdate(
                    kind="error",
                    payload={
                        "message": f"Aborted by {stop_key_label(self._settings.stop_key)} key."
                    },
                )
            )
            return

        elapsed = time.monotonic() - self._window_wait_started
        if elapsed > WINDOW_TIMEOUT:
            self._stop_window_wait()
            self._updates.put(
                ScanUpdate(
                    kind="error",
                    payload={
                        "message": f"Timed out waiting for active window {TARGET_APP!r}"
                    },
                )
            )
            return

        window = get_active_target_window()
        if window is None:
            return
        try:
            snapshot = build_window_snapshot(window)
        except Exception as exc:
            self._stop_window_wait()
            message = _format_exception_for_ui(
                exc, context="Failed to read target window information."
            )
            self._updates.put(ScanUpdate(kind="error", payload={"message": message}))
            return

        self._stop_window_wait()
        self._start_scan(snapshot)

    def _start_scan(self, window_snapshot: WindowSnapshot) -> None:
        if self._scan_started:
            return
        self._scan_started = True
        thread = threading.Thread(
            target=self._run_scan, args=(window_snapshot,), daemon=True
        )
        thread.start()

    def _run_scan(self, window_snapshot: WindowSnapshot) -> None:
        settings = self._settings
        try:
            from ..core.item_actions import ITEM_RULES_PATH
            from ..interaction.ui_windows import (
                SCROLL_CLICKS_PER_PAGE,
            )
            from ..ocr.inventory_vision import enable_ocr_debug
            from ..scanner.engine import scan_inventory

            scroll_clicks_default = (
                settings.scroll_clicks_per_page
                if settings.scroll_clicks_per_page is not None
                else SCROLL_CLICKS_PER_PAGE
            )
            scroll_clicks_alt_default = (
                settings.scroll_clicks_alt_per_page
                if settings.scroll_clicks_alt_per_page is not None
                else (scroll_clicks_default + 1)
            )

            if settings.debug_ocr:
                enable_ocr_debug(Path("ocr_debug"))

            progress = TextualScanProgress(self._updates)
            results, stats = scan_inventory(
                show_progress=False,
                scroll_clicks_per_page=scroll_clicks_default,
                scroll_clicks_alt_per_page=scroll_clicks_alt_default,
                apply_actions=not self.dry_run,
                actions_path=ITEM_RULES_PATH,
                profile_timing=settings.profile,
                stop_key=settings.stop_key,
                action_delay_ms=settings.action_delay_ms,
                menu_appear_delay_ms=settings.menu_appear_delay_ms,
                sell_recycle_post_delay_ms=settings.sell_recycle_post_delay_ms,
                infobox_retries=settings.infobox_retries,
                infobox_retry_delay_ms=settings.infobox_retry_delay_ms,
                ocr_unreadable_retries=settings.ocr_unreadable_retries,
                ocr_unreadable_retry_delay_ms=settings.ocr_unreadable_retry_delay_ms,
                progress=progress,
                window_snapshot=window_snapshot,
            )
        except KeyboardInterrupt:
            self._updates.put(
                ScanUpdate(
                    kind="error",
                    payload={
                        "message": f"Aborted by {stop_key_label(settings.stop_key)} key."
                    },
                )
            )
            return
        except ValueError as exc:
            self._updates.put(
                ScanUpdate(kind="error", payload={"message": f"Error: {exc}"})
            )
            return
        except TimeoutError as exc:
            self._updates.put(ScanUpdate(kind="error", payload={"message": str(exc)}))
            return
        except RuntimeError as exc:
            self._updates.put(
                ScanUpdate(kind="error", payload={"message": f"Fatal: {exc}"})
            )
            return
        except Exception as exc:  # pragma: no cover - safety net
            message = _format_exception_for_ui(
                exc, context="Unexpected error while scanning."
            )
            self._updates.put(ScanUpdate(kind="error", payload={"message": message}))
            return

        self._updates.put(
            ScanUpdate(kind="done", payload={"results": results, "stats": stats})
        )

    def _drain_updates(self) -> None:
        dirty = False
        while True:
            try:
                update = self._updates.get_nowait()
            except queue.Empty:
                break
            dirty = True
            kind = update.kind
            payload = update.payload
            if kind == "phase":
                self._state.phase = str(payload.get("phase", ""))
            elif kind == "mode":
                self._state.mode_label = str(payload.get("mode_label", ""))
            elif kind == "stash":
                self._state.stash_label = str(payload.get("stash_label", ""))
            elif kind == "pages":
                self._state.pages_label = str(payload.get("pages_label", ""))
            elif kind == "total":
                total = payload.get("total")
                self._state.total = int(total) if isinstance(total, int) else None
            elif kind == "timer":
                self._state.start_time = time.perf_counter()
            elif kind == "event":
                message = str(payload.get("message", ""))
                style = str(payload.get("style", "dim"))
                timestamp = datetime.now().strftime("%H:%M:%S")
                line = Text()
                line.append(timestamp, style="dim")
                line.append(" - ", style="dim")
                line.append(message, style=style)
                self._state.events.append(line)
            elif kind == "item":
                self._state.completed += 1
                self._state.current_label = str(payload.get("current_label", ""))
                self._state.last_item_label = str(payload.get("item_label", ""))
                outcome = str(payload.get("outcome", ""))
                self._state.last_outcome_label = outcome
                if outcome:
                    self._state.counts[outcome] += 1
            elif kind == "error":
                self._scan_complete = True
                message = str(payload.get("message", "Scan failed."))
                self.app.push_screen(MessageScreen(message, title="Scan stopped"))
                if self._scan_update_timer is not None:
                    self._scan_update_timer.pause()
                return
            elif kind == "done":
                self._scan_complete = True
                self._results = payload.get("results", [])
                self._stats = payload.get("stats")
                if self._scan_update_timer is not None:
                    self._scan_update_timer.pause()
                if self._stats is not None:
                    self.app.push_screen(
                        ScanResultsScreen(
                            results=self._results,
                            stats=self._stats,
                            dry_run=self.dry_run,
                        )
                    )
                return

        if self._state.start_time is not None:
            dirty = True
        if dirty:
            self._refresh_panels()

    def _refresh_panels(self) -> None:
        self.query_one("#scan-status", Static).update(self._render_status())
        self.query_one("#scan-last", Static).update(self._render_last_item())
        self.query_one("#scan-progress", Static).update(self._render_progress())
        self.query_one("#scan-counts", Static).update(self._render_counts())
        self.query_one("#scan-events", Static).update(self._render_events())

    def _render_status(self) -> Text:
        text = Text()
        text.append("Status\n", style="bold")
        if self._state.mode_label:
            text.append("Mode: ", style="cyan")
            text.append(self._state.mode_label)
            text.append("\n")
        text.append("Phase: ", style="cyan")
        text.append(self._state.phase or "Scanning")
        text.append("\n")
        if self._state.stash_label:
            text.append("Stash: ", style="cyan")
            text.append(self._state.stash_label)
            text.append("\n")
        if self._state.pages_label:
            text.append("Pages: ", style="cyan")
            text.append(self._state.pages_label)
            text.append("\n")
        if self._state.start_time is not None:
            elapsed = time.perf_counter() - self._state.start_time
            text.append("Elapsed: ", style="cyan")
            text.append(_format_duration(elapsed))
            text.append("\n")
            speed = self._speed(elapsed)
            if speed is not None:
                text.append("Speed: ", style="cyan")
                text.append(f"{speed:0.2f} it/s")
                text.append("\n")
            eta = self._eta_label(speed, elapsed)
            if eta:
                text.append("ETA: ", style="cyan")
                text.append(eta)
                text.append("\n")
        return text

    def _render_last_item(self) -> Text:
        text = Text()
        text.append("Last Item\n", style="bold")
        if self._state.current_label:
            text.append("Current: ", style="cyan")
            text.append(self._state.current_label)
            text.append("\n")
        if self._state.last_item_label:
            text.append("Item: ", style="cyan")
            text.append(self._state.last_item_label)
            text.append("\n")
        if self._state.last_outcome_label:
            text.append("Outcome: ", style="cyan")
            text.append(
                self._state.last_outcome_label,
                style=_outcome_style(self._state.last_outcome_label),
            )
            text.append("\n")
        if not self._state.last_item_label and not self._state.last_outcome_label:
            text.append("Waiting for first item...", style="dim")
        return text

    def _render_progress(self) -> Text:
        text = Text()
        text.append("Progress\n", style="bold")
        total = self._state.total
        completed = self._state.completed
        if total is None or total <= 0:
            bar = self._progress_bar(0.0)
            text.append(bar, style="cyan")
            text.append(f" {completed}/?", style="white")
            return text
        ratio = completed / total if total else 0.0
        ratio = min(max(ratio, 0.0), 1.0)
        bar = self._progress_bar(ratio)
        percent = ratio * 100.0
        text.append(bar, style="cyan")
        text.append(f" {completed}/{total}", style="white")
        text.append(f" ({percent:0.0f}%)", style="dim")
        return text

    def _render_counts(self) -> Text:
        text = Text()
        text.append("Outcomes\n", style="bold")
        if not self._state.counts:
            text.append("No items processed yet.", style="dim")
            return text
        ordered = [
            "KEEP",
            "RECYCLE",
            "SELL",
            "DRY-KEEP",
            "DRY-RECYCLE",
            "DRY-SELL",
            "UNREADABLE",
            "SKIP",
        ]
        for key in ordered:
            if key not in self._state.counts:
                continue
            text.append(f"{key}: ", style=_outcome_style(key))
            text.append(str(self._state.counts[key]))
            text.append("\n")
        for key in sorted(set(self._state.counts.keys()) - set(ordered)):
            text.append(f"{key}: ", style=_outcome_style(key))
            text.append(str(self._state.counts[key]))
            text.append("\n")
        return text

    def _render_events(self) -> Text:
        text = Text()
        text.append("Events\n", style="bold")
        if not self._state.events:
            text.append("No events yet.", style="dim")
            return text
        for line in self._state.events:
            text.append(line)
            text.append("\n")
        return text

    def _progress_bar(self, ratio: float, width: int = 32) -> str:
        ratio = min(max(ratio, 0.0), 1.0)
        filled = int(width * ratio)
        return f"[{'#' * filled}{'-' * (width - filled)}]"

    def _speed(self, elapsed: float) -> Optional[float]:
        if elapsed <= 0 or self._state.completed <= 0:
            return None
        return self._state.completed / elapsed

    def _eta_label(self, speed: Optional[float], elapsed: float) -> str:
        if speed is None or speed <= 0:
            return ""
        total = self._state.total
        if total is None:
            return ""
        remaining = max(0.0, float(total) - float(self._state.completed))
        seconds = remaining / speed if speed > 0 else 0
        eta = datetime.now() + timedelta(seconds=seconds)
        return eta.strftime("%H:%M:%S")


class ScanResultsScreen(AppScreen):
    BINDINGS = [*AppScreen.BINDINGS]

    def __init__(
        self,
        *,
        results: list["ItemActionResult"],
        stats: ScanStats,
        dry_run: bool,
    ) -> None:
        super().__init__()
        self._results = results
        self._stats = stats
        self._dry_run = dry_run

    def compose(self) -> ComposeResult:
        title = "Scan results (Dry Run)" if self._dry_run else "Scan results"
        yield Static(title, classes="menu-title")
        yield Static(self._build_overview(), id="scan-summary")
        if not self._results:
            yield Static("No results to display.", classes="hint")
        else:
            yield DataTable(id="scan-results-table")
        yield Footer()

    def on_mount(self) -> None:
        if not self._results:
            return
        table = self.query_one("#scan-results-table", DataTable)
        table.add_columns("Pg", "Idx", "Cell", "Item", "Outcome", "Notes")
        for result in self._results:
            outcome_label, details = _describe_action(result.action_taken)
            if result.decision and not outcome_label.startswith(result.decision):
                details.append(f"plan {result.decision}")
            if result.note:
                details.append(result.note)
            notes = "; ".join(details)
            global_idx = result.page * CELLS_PER_PAGE + result.cell.index
            table.add_row(
                f"{result.page + 1:02d}",
                f"{global_idx:03d}",
                f"r{result.cell.row}c{result.cell.col}",
                _item_label(result),
                outcome_label,
                notes,
            )
        table.focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _build_overview(self) -> Text:
        text = Text()
        text.append("Overview\n", style="bold")
        stash_label = (
            str(self._stats.items_in_stash)
            if self._stats.items_in_stash is not None
            else "?"
        )
        text.append("Items in stash: ", style="cyan")
        text.append(stash_label)
        text.append("\n")
        text.append("Items processed: ", style="cyan")
        text.append(str(len(self._results)))
        text.append("\n")
        planned_suffix = (
            f" (planned {self._stats.pages_planned})"
            if self._stats.pages_planned != self._stats.pages_scanned
            else ""
        )
        text.append("4x5 pages run: ", style="cyan")
        text.append(f"{self._stats.pages_scanned}{planned_suffix}")
        text.append("\n")
        text.append("Processing time: ", style="cyan")
        text.append(f"{self._stats.processing_seconds:.1f}s")
        if self._stats.items_in_stash is None and self._stats.stash_count_text:
            text.append("\n")
            text.append("Count OCR: ", style="cyan")
            text.append(self._stats.stash_count_text)
        text.append("\n")
        summary = self._summarize_results()
        text.append("Summary: ", style="cyan")
        parts = [f"{key}={summary[key]}" for key in self._ordered_summary(summary)]
        text.append(", ".join(parts))
        return text

    def _summarize_results(self) -> Counter[str]:
        summary: Counter[str] = Counter()
        for result in self._results:
            label, _ = _describe_action(result.action_taken)
            summary[label] += 1
        return summary

    def _ordered_summary(self, summary: Counter[str]) -> list[str]:
        ordered = [k for k in ("KEEP", "RECYCLE", "SELL") if k in summary]
        ordered += [k for k in ("DRY-KEEP", "DRY-RECYCLE", "DRY-SELL") if k in summary]
        if "UNREADABLE" in summary:
            ordered.append("UNREADABLE")
        if "SKIP" in summary:
            ordered.append("SKIP")
        ordered += sorted(set(summary.keys()) - set(ordered))
        return ordered
