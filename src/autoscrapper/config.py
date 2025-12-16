from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional


CONFIG_VERSION = 1
APP_CONFIG_DIR_NAME = "AutoScrapper"
CONFIG_FILE_NAME = "config.json"


PagesMode = Literal["auto", "manual"]


@dataclass(frozen=True)
class ScanSettings:
    pages_mode: PagesMode = "auto"
    pages: Optional[int] = None
    scroll_clicks_per_page: Optional[int] = None
    ocr_unreadable_retries: int = 1
    ocr_unreadable_retry_delay_ms: int = 100
    debug_ocr: bool = False
    profile: bool = False


def _config_dir() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_CONFIG_DIR_NAME
    return Path.home() / f".{APP_CONFIG_DIR_NAME.lower()}"


def config_path() -> Path:
    return _config_dir() / CONFIG_FILE_NAME


def _coerce_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_positive_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _coerce_non_negative_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _from_raw_scan_settings(raw: Any) -> ScanSettings:
    if not isinstance(raw, dict):
        return ScanSettings()

    pages_mode_raw = raw.get("pages_mode")
    pages_raw = raw.get("pages")
    scroll_clicks_raw = raw.get("scroll_clicks_per_page")
    ocr_unreadable_retries_raw = raw.get("ocr_unreadable_retries")
    ocr_unreadable_retry_delay_ms_raw = raw.get("ocr_unreadable_retry_delay_ms")

    pages = _coerce_positive_int(pages_raw)
    pages_mode: PagesMode
    if pages_mode_raw in ("auto", "manual"):
        pages_mode = pages_mode_raw
    else:
        pages_mode = "manual" if pages is not None else "auto"

    if pages_mode == "manual" and pages is None:
        pages_mode = "auto"
    if pages_mode == "auto":
        pages = None

    scroll_clicks_per_page = _coerce_non_negative_int(scroll_clicks_raw)

    ocr_unreadable_retries = _coerce_non_negative_int(ocr_unreadable_retries_raw)
    if ocr_unreadable_retries is None:
        ocr_unreadable_retries = ScanSettings.ocr_unreadable_retries

    ocr_unreadable_retry_delay_ms = _coerce_non_negative_int(ocr_unreadable_retry_delay_ms_raw)
    if ocr_unreadable_retry_delay_ms is None:
        ocr_unreadable_retry_delay_ms = ScanSettings.ocr_unreadable_retry_delay_ms

    return ScanSettings(
        pages_mode=pages_mode,
        pages=pages,
        scroll_clicks_per_page=scroll_clicks_per_page,
        ocr_unreadable_retries=ocr_unreadable_retries,
        ocr_unreadable_retry_delay_ms=ocr_unreadable_retry_delay_ms,
        debug_ocr=_coerce_bool(raw.get("debug_ocr"), False),
        profile=_coerce_bool(raw.get("profile"), False),
    )


def load_scan_settings() -> ScanSettings:
    path = config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ScanSettings()
    except (OSError, json.JSONDecodeError):
        return ScanSettings()

    if not isinstance(raw, dict):
        return ScanSettings()

    scan_raw = raw.get("scan")
    return _from_raw_scan_settings(scan_raw)


def save_scan_settings(settings: ScanSettings) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "version": CONFIG_VERSION,
        "scan": asdict(settings),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def reset_scan_settings() -> None:
    save_scan_settings(ScanSettings())
