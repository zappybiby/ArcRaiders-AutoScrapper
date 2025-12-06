from __future__ import annotations

from ..inventory_scanner import main as _scanner_main


def main(argv=None) -> int:
    """
    Entrypoint wrapper that delegates execution to the inventory scanner.
    
    Parameters:
        argv (optional): Sequence of command-line arguments to pass to the scanner; when `None` the scanner's default argument handling is used.
    
    Returns:
        int: Exit code returned by the inventory scanner.
    """
    return _scanner_main(argv)