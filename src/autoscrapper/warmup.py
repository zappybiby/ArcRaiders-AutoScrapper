from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass
from typing import Optional

_WARMUP_LOCK = threading.Lock()
_WARMUP_DONE = threading.Event()
_WARMUP_STARTED = False
_WARMUP_ERROR: Optional[str] = None

_HEAVY_MODULES = (
    "autoscrapper.core.item_actions",
    "autoscrapper.interaction.ui_windows",
    "autoscrapper.ocr.inventory_vision",
    "autoscrapper.scanner.scan_loop",
    "autoscrapper.scanner.engine",
)


@dataclass(frozen=True)
class WarmupStatus:
    started: bool
    completed: bool
    failed: bool
    error: Optional[str]


def _set_warmup_error(error: Optional[str]) -> None:
    global _WARMUP_ERROR
    with _WARMUP_LOCK:
        _WARMUP_ERROR = error


def _get_warmup_error() -> Optional[str]:
    with _WARMUP_LOCK:
        return _WARMUP_ERROR


def _run_background_warmup() -> None:
    try:
        for module_name in _HEAVY_MODULES:
            importlib.import_module(module_name)
        from .ocr.tesseract import initialize_ocr

        initialize_ocr()
    except Exception as exc:  # pragma: no cover - defensive warmup fallback
        _set_warmup_error(f"{type(exc).__name__}: {exc}")
    finally:
        _WARMUP_DONE.set()


def start_background_warmup() -> None:
    global _WARMUP_STARTED
    with _WARMUP_LOCK:
        if _WARMUP_STARTED:
            return
        _WARMUP_STARTED = True
        thread = threading.Thread(
            target=_run_background_warmup,
            name="autoscrapper-warmup",
            daemon=True,
        )
        thread.start()


def warmup_status() -> WarmupStatus:
    with _WARMUP_LOCK:
        started = _WARMUP_STARTED
    error = _get_warmup_error()
    completed = _WARMUP_DONE.is_set()
    return WarmupStatus(
        started=started,
        completed=completed,
        failed=error is not None,
        error=error,
    )
