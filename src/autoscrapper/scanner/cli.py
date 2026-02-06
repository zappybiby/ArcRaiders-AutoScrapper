from __future__ import annotations

import argparse
from typing import Iterable, Optional


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoscrapper scan",
        description="Open the Textual scan interface directly.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only; log planned actions without clicking sell/recycle.",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    from ..tui import run_tui

    return run_tui(start_screen="scan", dry_run=args.dry_run)
