from __future__ import annotations

from collections import Counter
from typing import List, Optional

from .outcomes import _describe_action, _outcome_style
from .rich_support import Console, Table, Text, box
from .types import ScanStats
from ..core.item_actions import ItemActionResult


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
    ordered_keys = [k for k in ("KEEP", "RECYCLE", "SELL") if k in summary]
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
    results: List[ItemActionResult],
    cells_per_page: int,
    stats: ScanStats,
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
