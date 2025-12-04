from __future__ import annotations

from ..inventory_scanner import main as _scanner_main


def main(argv=None) -> int:
    """
    Wrapper entrypoint for the inventory scanner.
    """
    return _scanner_main(argv)
