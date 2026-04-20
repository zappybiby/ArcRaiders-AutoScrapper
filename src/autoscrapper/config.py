from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import orjson

from .interaction.keybinds import DEFAULT_STOP_KEY, normalize_stop_key

CONFIG_VERSION = 6

_MAX_DELAY_MS = 5000
_MAX_RETRY_COUNT = 10

_log = logging.getLogger(__name__)
APP_CONFIG_DIR_NAME = "AutoScrapper"
CONFIG_FILE_NAME = "config.json"


type ConfigDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScanSettings:
    stop_key: str = DEFAULT_STOP_KEY
    infobox_retries: int = 3
    infobox_retry_interval_ms: int = 50
    ocr_unreadable_retries: int = 1
    ocr_retry_interval_ms: int = 50
    input_action_delay_ms: int = 100
    cell_infobox_left_right_click_gap_ms: int = 250
    item_infobox_settle_delay_ms: int = 200
    post_sell_recycle_delay_ms: int = 100
    debug_ocr: bool = False
    profile: bool = False


@dataclass(frozen=True, slots=True)
class ProgressSettings:
    all_quests_completed: bool = False
    active_quests: list[str] = field(default_factory=list)
    completed_quests: list[str] = field(default_factory=list)
    hideout_levels: dict[str, int] = field(default_factory=dict)
    last_updated: str | None = None


@dataclass(frozen=True, slots=True)
class UiSettings:
    default_rules_warning_shown: bool = False


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """ArcTracker API configuration."""

    app_key: str = ""
    user_key: str = ""
    enabled: bool = False
    prefer_api: bool = True
    base_url: str = "https://arctracker.io"


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


def _coerce_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _coerce_non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _clamp_delay_ms(value: int, field_name: str) -> int:
    if value > _MAX_DELAY_MS:
        _log.warning(
            "config: %s=%d exceeds maximum %d ms; clamping to %d",
            field_name,
            value,
            _MAX_DELAY_MS,
            _MAX_DELAY_MS,
        )
        return _MAX_DELAY_MS
    return value


def _clamp_retry_count(value: int, field_name: str) -> int:
    if value > _MAX_RETRY_COUNT:
        _log.warning(
            "config: %s=%d exceeds maximum %d; clamping to %d",
            field_name,
            value,
            _MAX_RETRY_COUNT,
            _MAX_RETRY_COUNT,
        )
        return _MAX_RETRY_COUNT
    return value


def _raw_with_aliases(raw: ConfigDict, *keys: str) -> Any:
    for key in keys:
        if key in raw:
            return raw.get(key)
    return None


# ---------------------------------------------------------------------------
# Config version migration
# ---------------------------------------------------------------------------


def _migrate_v1_to_v2(payload: ConfigDict) -> ConfigDict:
    """Add progress settings section (v2)."""
    if "progress" not in payload:
        payload["progress"] = {
            "all_quests_completed": False,
            "active_quests": [],
            "completed_quests": [],
            "hideout_levels": {},
            "last_updated": None,
        }
    return payload


def _migrate_v2_to_v3(payload: ConfigDict) -> ConfigDict:
    """Add UI settings section (v3)."""
    if "ui" not in payload:
        payload["ui"] = {
            "default_rules_warning_shown": False,
        }
    return payload


def _migrate_v3_to_v4(payload: ConfigDict) -> ConfigDict:
    """Stub: no structural changes between v3 and v4."""
    return payload


def _migrate_v4_to_v5(payload: ConfigDict) -> ConfigDict:
    """Stub: no structural changes between v4 and v5."""
    return payload


def _migrate_v5_to_v6(payload: ConfigDict) -> ConfigDict:
    """Add API settings section (v6)."""
    if "api" not in payload:
        payload["api"] = {
            "app_key": "",
            "user_key": "",
            "enabled": False,
            "prefer_api": True,
            "base_url": "https://arctracker.io",
        }
    return payload


type MigrateFn = Callable[[ConfigDict], ConfigDict]

_MIGRATIONS: dict[int, MigrateFn] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
    5: _migrate_v5_to_v6,
}


def _migrate_config(payload: ConfigDict) -> ConfigDict:
    """
    Walk the payload from its stored version up to CONFIG_VERSION,
    applying each migration step in sequence.  Warns if the stored
    version is unknown or ahead of the current code.
    """
    stored_version = payload.get("version")
    if not isinstance(stored_version, int):
        return payload

    if stored_version > CONFIG_VERSION:
        _log.warning(
            "config: stored version %d is newer than current code version %d; "
            "loading as-is — some settings may be ignored",
            stored_version,
            CONFIG_VERSION,
        )
        return payload

    if stored_version < CONFIG_VERSION:
        _log.warning(
            "config: stored version %d is older than current version %d; migrating automatically",
            stored_version,
            CONFIG_VERSION,
        )
        for from_version in range(stored_version, CONFIG_VERSION):
            migrate_fn = _MIGRATIONS.get(from_version)
            if migrate_fn is not None:
                payload = migrate_fn(payload)
        payload["version"] = CONFIG_VERSION

    return payload


def _load_config_dict() -> ConfigDict:
    path = config_path()
    try:
        raw = orjson.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, orjson.JSONDecodeError):
        return {}

    if not isinstance(raw, dict):
        return {}

    return _migrate_config(raw)


def _save_config_dict(payload: ConfigDict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def _from_raw_scan_settings(raw: Any) -> ScanSettings:
    if not isinstance(raw, dict):
        return ScanSettings()

    stop_key_raw = raw.get("stop_key")
    infobox_retries_raw = raw.get("infobox_retries")
    infobox_retry_interval_ms_raw = _raw_with_aliases(
        raw,
        "infobox_retry_interval_ms",
        "infobox_retry_delay_ms",
    )
    ocr_unreadable_retries_raw = raw.get("ocr_unreadable_retries")
    ocr_retry_interval_ms_raw = _raw_with_aliases(
        raw,
        "ocr_retry_interval_ms",
        "ocr_unreadable_retry_delay_ms",
    )
    input_action_delay_ms_raw = _raw_with_aliases(
        raw,
        "input_action_delay_ms",
        "action_delay_ms",
    )
    cell_infobox_left_right_click_gap_ms_raw = raw.get("cell_infobox_left_right_click_gap_ms")
    item_infobox_settle_delay_ms_raw = _raw_with_aliases(
        raw,
        "item_infobox_settle_delay_ms",
        "menu_appear_delay_ms",
    )
    post_sell_recycle_delay_ms_raw = _raw_with_aliases(
        raw,
        "post_sell_recycle_delay_ms",
        "sell_recycle_post_delay_ms",
    )

    infobox_retries = _coerce_positive_int(infobox_retries_raw)
    if infobox_retries is None:
        infobox_retries = ScanSettings.infobox_retries
    infobox_retries = _clamp_retry_count(infobox_retries, "infobox_retries")

    infobox_retry_interval_ms = _coerce_non_negative_int(infobox_retry_interval_ms_raw)
    if infobox_retry_interval_ms is None:
        infobox_retry_interval_ms = ScanSettings.infobox_retry_interval_ms
    infobox_retry_interval_ms = _clamp_delay_ms(infobox_retry_interval_ms, "infobox_retry_interval_ms")

    ocr_unreadable_retries = _coerce_non_negative_int(ocr_unreadable_retries_raw)
    if ocr_unreadable_retries is None:
        ocr_unreadable_retries = ScanSettings.ocr_unreadable_retries
    ocr_unreadable_retries = _clamp_retry_count(ocr_unreadable_retries, "ocr_unreadable_retries")

    ocr_retry_interval_ms = _coerce_non_negative_int(ocr_retry_interval_ms_raw)
    if ocr_retry_interval_ms is None:
        ocr_retry_interval_ms = ScanSettings.ocr_retry_interval_ms
    ocr_retry_interval_ms = _clamp_delay_ms(ocr_retry_interval_ms, "ocr_retry_interval_ms")

    input_action_delay_ms = _coerce_non_negative_int(input_action_delay_ms_raw)
    if input_action_delay_ms is None:
        input_action_delay_ms = ScanSettings.input_action_delay_ms
    input_action_delay_ms = _clamp_delay_ms(input_action_delay_ms, "input_action_delay_ms")

    cell_infobox_left_right_click_gap_ms = _coerce_non_negative_int(cell_infobox_left_right_click_gap_ms_raw)
    if cell_infobox_left_right_click_gap_ms is None:
        cell_infobox_left_right_click_gap_ms = ScanSettings.cell_infobox_left_right_click_gap_ms
    cell_infobox_left_right_click_gap_ms = _clamp_delay_ms(
        cell_infobox_left_right_click_gap_ms, "cell_infobox_left_right_click_gap_ms"
    )

    item_infobox_settle_delay_ms = _coerce_non_negative_int(item_infobox_settle_delay_ms_raw)
    if item_infobox_settle_delay_ms is None:
        item_infobox_settle_delay_ms = ScanSettings.item_infobox_settle_delay_ms
    item_infobox_settle_delay_ms = _clamp_delay_ms(item_infobox_settle_delay_ms, "item_infobox_settle_delay_ms")

    post_sell_recycle_delay_ms = _coerce_non_negative_int(post_sell_recycle_delay_ms_raw)
    if post_sell_recycle_delay_ms is None:
        post_sell_recycle_delay_ms = ScanSettings.post_sell_recycle_delay_ms
    post_sell_recycle_delay_ms = _clamp_delay_ms(post_sell_recycle_delay_ms, "post_sell_recycle_delay_ms")

    return ScanSettings(
        stop_key=normalize_stop_key(stop_key_raw),
        infobox_retries=infobox_retries,
        infobox_retry_interval_ms=infobox_retry_interval_ms,
        ocr_unreadable_retries=ocr_unreadable_retries,
        ocr_retry_interval_ms=ocr_retry_interval_ms,
        input_action_delay_ms=input_action_delay_ms,
        cell_infobox_left_right_click_gap_ms=cell_infobox_left_right_click_gap_ms,
        item_infobox_settle_delay_ms=item_infobox_settle_delay_ms,
        post_sell_recycle_delay_ms=post_sell_recycle_delay_ms,
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

    active_quests = [str(q) for q in active_quests_raw if str(q).strip()] if isinstance(active_quests_raw, list) else []
    completed_quests = (
        [str(q) for q in completed_quests_raw if str(q).strip()] if isinstance(completed_quests_raw, list) else []
    )
    hideout_levels: dict[str, int] = {}
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
        last_updated=(str(last_updated_raw) if isinstance(last_updated_raw, str) else None),
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
        settings.all_quests_completed or settings.active_quests or settings.completed_quests or settings.hideout_levels
    )


def _from_raw_ui_settings(raw: Any) -> UiSettings:
    if not isinstance(raw, dict):
        return UiSettings()
    return UiSettings(default_rules_warning_shown=_coerce_bool(raw.get("default_rules_warning_shown"), False))


def load_ui_settings() -> UiSettings:
    return _from_raw_ui_settings(_load_config_dict().get("ui"))


def save_ui_settings(settings: UiSettings) -> None:
    payload = _load_config_dict()
    payload["version"] = CONFIG_VERSION
    payload["ui"] = asdict(settings)
    _save_config_dict(payload)


def _from_raw_api_settings(raw: Any) -> ApiSettings:
    if not isinstance(raw, dict):
        return ApiSettings()
    return ApiSettings(
        app_key=str(raw.get("app_key", "")),
        user_key=str(raw.get("user_key", "")),
        enabled=_coerce_bool(raw.get("enabled"), False),
        prefer_api=_coerce_bool(raw.get("prefer_api"), True),
        base_url=str(raw.get("base_url", "https://arctracker.io")),
    )


def load_api_settings() -> ApiSettings:
    return _from_raw_api_settings(_load_config_dict().get("api"))


def save_api_settings(settings: ApiSettings) -> None:
    payload = _load_config_dict()
    payload["version"] = CONFIG_VERSION
    payload["api"] = asdict(settings)
    _save_config_dict(payload)


def reset_api_settings() -> None:
    save_api_settings(ApiSettings())
