from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from .engine import scan_inventory
from .report import _render_results
from ..config import load_scan_settings
from ..core.item_actions import ITEM_RULES_PATH
from ..cli.warnings import maybe_warn_default_rules
from ..interaction.keybinds import stop_key_label
from ..interaction.inventory_grid import Grid
from ..interaction.ui_windows import SCROLL_CLICKS_PER_PAGE
from ..ocr.inventory_vision import enable_ocr_debug


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

    maybe_warn_default_rules()

    if args.debug_ocr:
        enable_ocr_debug(Path("ocr_debug"))

    try:
        results, stats = scan_inventory(
            show_progress=True,
            pages=args.pages,
            scroll_clicks_per_page=args.scroll_clicks,
            apply_actions=not args.dry_run,
            actions_path=ITEM_RULES_PATH,
            profile_timing=args.profile,
            stop_key=settings.stop_key,
            action_delay_ms=settings.action_delay_ms,
            menu_appear_delay_ms=settings.menu_appear_delay_ms,
            sell_recycle_post_delay_ms=settings.sell_recycle_post_delay_ms,
            infobox_retries=settings.infobox_retries,
            infobox_retry_delay_ms=settings.infobox_retry_delay_ms,
            ocr_unreadable_retries=settings.ocr_unreadable_retries,
            ocr_unreadable_retry_delay_ms=settings.ocr_unreadable_retry_delay_ms,
        )
    except KeyboardInterrupt:
        print(f"Aborted by {stop_key_label(settings.stop_key)} key.")
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
