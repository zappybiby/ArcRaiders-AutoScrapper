from __future__ import annotations

from ..items.rules_cli import main as _rules_main


def main(argv=None) -> int:
    """
    Provide a CLI wrapper that invokes the item rules manager.
    
    Parameters:
        argv (Sequence[str] | None): Optional argument vector accepted for CLI compatibility; ignored by this wrapper.
    
    Returns:
        int: Exit status code, always 0.
    """
    _rules_main()
    return 0