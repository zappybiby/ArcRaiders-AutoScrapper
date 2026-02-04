from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .interaction.keybinds import DEFAULT_STOP_KEY, normalize_stop_key

CONFIG_VERSION = 3
APP_CONFIG_DIR_NAME = "AutoScrapper"
CONFIG_FILE_NAME = "config.json"


@dataclass(frozen=True)
class ScanSettings:
    scroll_clicks_per_page: Optional[int] = None
    scroll_clicks_alt_per_page: Optional[int] = None
    stop_key: str = DEFAULT_STOP_KEY
    infobox_retries: int = 3
    infobox_retry_delay_ms: int = 100
    ocr_unreadable_retries: int = 1
    ocr_unreadable_retry_delay_ms: int = 100
    action_delay_ms: int = 50
    menu_appear_delay_ms: int = 150
    sell_recycle_post_delay_ms: int = 100
    debug_ocr: bool = False
    profile: bool = False


@dataclass(frozen=True)
class ProgressSettings:
    all_quests_completed: bool = False
    active_quests: list[str] = field(default_factory=list)
    completed_quests: list[str] = field(default_factory=list)
    hideout_levels: Dict[str, int] = field(default_factory=dict)
    last_updated: Optional[str] = None


@dataclass(frozen=True)
class UiSettings:
    default_rules_warning_shown: bool = False


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


def _load_config_dict() -> Dict[str, Any]:
    path = config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}

    return raw if isinstance(raw, dict) else {}


def _save_config_dict(payload: Dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _from_raw_scan_settings(raw: Any) -> ScanSettings:
    if not isinstance(raw, dict):
        return ScanSettings()

    scroll_clicks_raw = raw.get("scroll_clicks_per_page")
    scroll_clicks_alt_raw = raw.get("scroll_clicks_alt_per_page")
    stop_key_raw = raw.get("stop_key")
    infobox_retries_raw = raw.get("infobox_retries")
    infobox_retry_delay_ms_raw = raw.get("infobox_retry_delay_ms")
    ocr_unreadable_retries_raw = raw.get("ocr_unreadable_retries")
    ocr_unreadable_retry_delay_ms_raw = raw.get("ocr_unreadable_retry_delay_ms")
    action_delay_ms_raw = raw.get("action_delay_ms")
    menu_appear_delay_ms_raw = raw.get("menu_appear_delay_ms")
    sell_recycle_post_delay_ms_raw = raw.get("sell_recycle_post_delay_ms")

    scroll_clicks_per_page = _coerce_non_negative_int(scroll_clicks_raw)
    scroll_clicks_alt_per_page = _coerce_non_negative_int(scroll_clicks_alt_raw)

    infobox_retries = _coerce_positive_int(infobox_retries_raw)
    if infobox_retries is None:
        infobox_retries = ScanSettings.infobox_retries

    infobox_retry_delay_ms = _coerce_non_negative_int(infobox_retry_delay_ms_raw)
    if infobox_retry_delay_ms is None:
        infobox_retry_delay_ms = ScanSettings.infobox_retry_delay_ms

    ocr_unreadable_retries = _coerce_non_negative_int(ocr_unreadable_retries_raw)
    if ocr_unreadable_retries is None:
        ocr_unreadable_retries = ScanSettings.ocr_unreadable_retries

    ocr_unreadable_retry_delay_ms = _coerce_non_negative_int(
        ocr_unreadable_retry_delay_ms_raw
    )
    if ocr_unreadable_retry_delay_ms is None:
        ocr_unreadable_retry_delay_ms = ScanSettings.ocr_unreadable_retry_delay_ms

    action_delay_ms = _coerce_non_negative_int(action_delay_ms_raw)
    if action_delay_ms is None:
        action_delay_ms = ScanSettings.action_delay_ms

    menu_appear_delay_ms = _coerce_non_negative_int(menu_appear_delay_ms_raw)
    if menu_appear_delay_ms is None:
        menu_appear_delay_ms = ScanSettings.menu_appear_delay_ms

    sell_recycle_post_delay_ms = _coerce_non_negative_int(
        sell_recycle_post_delay_ms_raw
    )
    if sell_recycle_post_delay_ms is None:
        sell_recycle_post_delay_ms = ScanSettings.sell_recycle_post_delay_ms

    return ScanSettings(
        scroll_clicks_per_page=scroll_clicks_per_page,
        scroll_clicks_alt_per_page=scroll_clicks_alt_per_page,
        stop_key=normalize_stop_key(stop_key_raw),
        infobox_retries=infobox_retries,
        infobox_retry_delay_ms=infobox_retry_delay_ms,
        ocr_unreadable_retries=ocr_unreadable_retries,
        ocr_unreadable_retry_delay_ms=ocr_unreadable_retry_delay_ms,
        action_delay_ms=action_delay_ms,
        menu_appear_delay_ms=menu_appear_delay_ms,
        sell_recycle_post_delay_ms=sell_recycle_post_delay_ms,
        debug_ocr=_coerce_bool(raw.get("debug_ocr"), False),
        profile=_coerce_bool(raw.get("profile"), False),
    )


def load_scan_settings() -> ScanSettings:
    scan_raw = _load_config_dict().get("scan")
    return _from_raw_scan_settings(scan_raw)


def save_scan_settings(settings: ScanSettings) -> None:
    payload = _load_config_dict()
    payload["version"] = CONFIG_VERSION
    payload["scan"] = asdict(settings)
    _save_config_dict(payload)


def reset_scan_settings() -> None:
    save_scan_settings(ScanSettings())


def _from_raw_progress_settings(raw: Any) -> ProgressSettings:
    if not isinstance(raw, dict):
        return ProgressSettings()

    active_quests_raw = raw.get("active_quests")
    completed_quests_raw = raw.get("completed_quests")
    hideout_levels_raw = raw.get("hideout_levels")
    last_updated_raw = raw.get("last_updated")

    active_quests = (
        [str(q) for q in active_quests_raw if str(q).strip()]
        if isinstance(active_quests_raw, list)
        else []
    )
    completed_quests = (
        [str(q) for q in completed_quests_raw if str(q).strip()]
        if isinstance(completed_quests_raw, list)
        else []
    )
    hideout_levels: Dict[str, int] = {}
    if isinstance(hideout_levels_raw, dict):
        for key, value in hideout_levels_raw.items():
            try:
                level = int(value)
            except (TypeError, ValueError):
                continue
            hideout_levels[str(key)] = level

    return ProgressSettings(
        all_quests_completed=_coerce_bool(raw.get("all_quests_completed"), False),
        active_quests=active_quests,
        completed_quests=completed_quests,
        hideout_levels=hideout_levels,
        last_updated=(
            str(last_updated_raw) if isinstance(last_updated_raw, str) else None
        ),
    )


def load_progress_settings() -> ProgressSettings:
    return _from_raw_progress_settings(_load_config_dict().get("progress"))


def save_progress_settings(settings: ProgressSettings) -> None:
    payload = _load_config_dict()
    payload["version"] = CONFIG_VERSION
    payload["progress"] = asdict(settings)
    _save_config_dict(payload)


def reset_progress_settings() -> None:
    payload = _load_config_dict()
    payload["version"] = CONFIG_VERSION
    payload["progress"] = asdict(ProgressSettings())
    _save_config_dict(payload)


def has_saved_progress(settings: ProgressSettings) -> bool:
    return bool(
        settings.all_quests_completed
        or settings.active_quests
        or settings.completed_quests
        or settings.hideout_levels
    )


def _from_raw_ui_settings(raw: Any) -> UiSettings:
    if not isinstance(raw, dict):
        return UiSettings()
    return UiSettings(
        default_rules_warning_shown=_coerce_bool(
            raw.get("default_rules_warning_shown"), False
        )
    )


def load_ui_settings() -> UiSettings:
    return _from_raw_ui_settings(_load_config_dict().get("ui"))


def save_ui_settings(settings: UiSettings) -> None:
    payload = _load_config_dict()
    payload["version"] = CONFIG_VERSION
    payload["ui"] = asdict(settings)
    _save_config_dict(payload)
