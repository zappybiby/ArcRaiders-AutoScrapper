from __future__ import annotations

from ..items.rules_viewer import run_rules_viewer


def main(argv=None) -> int:
    """
    Wrapper entrypoint for the item rules viewer.
    """
    _ = argv
    return run_rules_viewer()
