from __future__ import annotations

from ..items.rules_cli import main as _rules_main


def main(argv=None) -> int:
    """
    Wrapper entrypoint for the item rules manager.
    """
    _rules_main()
    return 0
