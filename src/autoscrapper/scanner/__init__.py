from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import scan_inventory
    from .types import ScanStats

__all__ = ["ScanStats", "scan_inventory"]


def __getattr__(name: str):
    if name == "ScanStats":
        from .types import ScanStats as _scan_stats

        return _scan_stats
    if name == "scan_inventory":
        from .engine import scan_inventory as _scan_inventory

        return _scan_inventory
    raise AttributeError(f"module 'autoscrapper.scanner' has no attribute {name!r}")
