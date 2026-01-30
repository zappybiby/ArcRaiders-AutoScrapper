"""
inventory_scanner.py

Scan the 4x5 inventory grid by hovering each cell, opening the context
menu, locating the light infobox (#f9eedf), and OCR-ing the item title.
"""

from __future__ import annotations

from .scanner.cli import main
from .scanner.engine import scan_inventory
from .scanner.types import ScanStats

__all__ = ["ScanStats", "main", "scan_inventory"]
