from __future__ import annotations

import time
from collections import Counter, deque
from datetime import datetime, timedelta
from typing import Optional

from .outcomes import _outcome_style
from .rich_support import (
    Align,
    BarColumn,
    Console,
    Group,
    Live,
    Panel,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Table,
    Task,
    TaskProgressColumn,
    Text,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    box,
)

# ---------------------------------------------------------------------------
# Live scan UI
# ---------------------------------------------------------------------------

AUTOSCRAPPER_ASCII = r"""
    ___       __       ____
  / _ |__ __/ /____  / __/__________ ____  ___  ___ ____
 / __ / // / __/ _ \_\ \/ __/ __/ _ `/ _ \/ _ \/ -_) __/
/_/ |_|\_,_/\__/\___/___/\__/_/  \_,_/ .__/ .__/\__/_/
                                   /_/  /_/
""".strip("\n")


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
