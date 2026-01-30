from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScanStats:
    """
    Aggregate metrics for the scan useful for reporting.
    """

    items_in_stash: Optional[int]
    stash_count_text: str
    pages_planned: int
    pages_scanned: int
    processing_seconds: float
