from __future__ import annotations

from typing import Optional

from .live_ui import _ScanLiveUI
from .rich_support import Console


class ScanProgress:
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def set_total(self, total: Optional[int]) -> None:
        raise NotImplementedError

    def set_phase(self, phase: str) -> None:
        raise NotImplementedError

    def set_mode(self, mode_label: str) -> None:
        raise NotImplementedError

    def set_stash_label(self, stash_label: str) -> None:
        raise NotImplementedError

    def set_pages_label(self, pages_label: str) -> None:
        raise NotImplementedError

    def start_timer(self) -> None:
        raise NotImplementedError

    def add_event(self, message: str, *, style: str = "dim") -> None:
        raise NotImplementedError

    def update_item(self, current_label: str, item_label: str, outcome: str) -> None:
        raise NotImplementedError


class NullScanProgress(ScanProgress):
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def set_total(self, total: Optional[int]) -> None:
        return None

    def set_phase(self, phase: str) -> None:
        return None

    def set_mode(self, mode_label: str) -> None:
        return None

    def set_stash_label(self, stash_label: str) -> None:
        return None

    def set_pages_label(self, pages_label: str) -> None:
        return None

    def start_timer(self) -> None:
        return None

    def add_event(self, message: str, *, style: str = "dim") -> None:
        return None

    def update_item(self, current_label: str, item_label: str, outcome: str) -> None:
        return None


class RichScanProgress(ScanProgress):
    def __init__(self) -> None:
        if Console is None:
            raise RuntimeError("Rich is required for the live scan UI.")
        self._ui = _ScanLiveUI()

    def start(self) -> None:
        self._ui.start()

    def stop(self) -> None:
        self._ui.stop()

    def set_total(self, total: Optional[int]) -> None:
        self._ui.set_total(total)

    def set_phase(self, phase: str) -> None:
        self._ui.set_phase(phase)

    def set_mode(self, mode_label: str) -> None:
        self._ui.mode_label = mode_label
        self._ui.refresh()

    def set_stash_label(self, stash_label: str) -> None:
        self._ui.stash_label = stash_label
        self._ui.refresh()

    def set_pages_label(self, pages_label: str) -> None:
        self._ui.pages_label = pages_label
        self._ui.refresh()

    def start_timer(self) -> None:
        self._ui.start_timer()

    def add_event(self, message: str, *, style: str = "dim") -> None:
        self._ui.add_event(message, style=style)

    def update_item(self, current_label: str, item_label: str, outcome: str) -> None:
        self._ui.update_item(current_label, item_label, outcome)
