import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from autoscrapper.config import (
    CONFIG_VERSION,
    _load_config_dict,
    _migrate_config,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
    _migrate_v5_to_v6,
)


def test_migrate_v1_to_v2():
    """Test that v1 to v2 migration adds the progress section."""
    payload = {"version": 1}
    result = _migrate_v1_to_v2(payload.copy())
    assert "progress" in result
    assert result["progress"]["all_quests_completed"] is False
    assert result["progress"]["active_quests"] == []


def test_migrate_v1_to_v2_idempotent():
    """Test that v1 to v2 migration does not overwrite existing progress section."""
    payload = {"version": 1, "progress": {"all_quests_completed": True}}
    result = _migrate_v1_to_v2(payload.copy())
    assert result["progress"]["all_quests_completed"] is True


def test_migrate_v2_to_v3():
    """Test that v2 to v3 migration adds the ui section."""
    payload = {"version": 2}
    result = _migrate_v2_to_v3(payload.copy())
    assert "ui" in result
    assert result["ui"]["default_rules_warning_shown"] is False


def test_migrate_v2_to_v3_idempotent():
    """Test that v2 to v3 migration does not overwrite existing ui section."""
    payload = {"version": 2, "ui": {"default_rules_warning_shown": True}}
    result = _migrate_v2_to_v3(payload.copy())
    assert result["ui"]["default_rules_warning_shown"] is True


def test_migrate_v5_to_v6():
    """Test that v5 to v6 migration adds the api section."""
    payload = {"version": 5}
    result = _migrate_v5_to_v6(payload.copy())
    assert "api" in result
    assert result["api"]["enabled"] is False
    assert result["api"]["base_url"] == "https://arctracker.io"


def test_migrate_v5_to_v6_idempotent():
    """Test that v5 to v6 migration does not overwrite existing api section."""
    payload = {"version": 5, "api": {"enabled": True}}
    result = _migrate_v5_to_v6(payload.copy())
    assert result["api"]["enabled"] is True


def test_migrate_full_chain():
    """Test that a v1 config is migrated through the entire chain to the current version."""
    payload = {"version": 1, "scan": {"debug_ocr": True}}
    result = _migrate_config(payload.copy())

    assert result["version"] == CONFIG_VERSION
    assert result["scan"]["debug_ocr"] is True
    assert "progress" in result
    assert "ui" in result
    assert "api" in result


def test_migrate_config_no_version():
    """Test that a payload without a version is returned as-is."""
    payload = {"some_key": "some_value"}
    result = _migrate_config(payload.copy())
    assert result == payload


def test_migrate_config_non_integer_version():
    """Test that a payload with a non-integer version is returned as-is."""
    payload = {"version": "1.0", "some_key": "some_value"}
    result = _migrate_config(payload.copy())
    assert result == payload


def test_migrate_config_current_version():
    """Test that a payload with the current version is returned as-is."""
    payload = {"version": CONFIG_VERSION, "some_key": "some_value"}
    result = _migrate_config(payload.copy())
    assert result == payload


def test_migrate_config_future_version():
    """Test that a payload with a future version is returned as-is, but a warning is logged."""
    payload = {"version": CONFIG_VERSION + 1, "some_key": "some_value"}
    result = _migrate_config(payload.copy())
    assert result == payload


def test_migrate_config_old_version():
    """Test that a payload with an old version is migrated to the current version."""
    # Assuming CONFIG_VERSION is at least 1 and we migrate from 1
    # We will test a version older than current
    if CONFIG_VERSION > 1:
        payload = {"version": 1, "some_key": "some_value"}
        result = _migrate_config(payload.copy())
        assert result["version"] == CONFIG_VERSION
        assert result["some_key"] == "some_value"


@patch("autoscrapper.config._log.warning")
def test_migrate_config_future_version_warning(mock_warning):
    """Test that a warning is logged for future versions."""
    future_version = CONFIG_VERSION + 1
    payload = {"version": future_version, "some_key": "some_value"}
    _migrate_config(payload.copy())
    mock_warning.assert_called_once()
    assert "newer than current code version" in mock_warning.call_args[0][0]
    assert mock_warning.call_args[0][1] == future_version
    assert mock_warning.call_args[0][2] == CONFIG_VERSION


def migrate_1_to_2(payload):
    payload["step_1_applied"] = True
    return payload


def migrate_2_to_3(payload):
    payload["step_2_applied"] = True
    return payload


def migrate_3_to_4(payload):
    payload["step_3_applied"] = True
    return payload


dummy_migrations = {
    1: migrate_1_to_2,
    2: migrate_2_to_3,
    3: migrate_3_to_4,
}


@patch("autoscrapper.config._MIGRATIONS", new=dummy_migrations)
@patch("autoscrapper.config.CONFIG_VERSION", 4)
def test_migrate_config_applies_all_steps():
    """Test that all migration steps are applied sequentially up to CONFIG_VERSION."""
    payload = {"version": 1}
    result = _migrate_config(payload)

    assert result["version"] == 4
    assert result.get("step_1_applied") is True
    assert result.get("step_2_applied") is True
    assert result.get("step_3_applied") is True


@patch("autoscrapper.config.config_path")
def test_load_config_dict_file_not_found(mock_config_path):
    """Test that _load_config_dict returns an empty dict if the file is not found."""
    mock_path = MagicMock(spec=Path)
    mock_path.read_bytes.side_effect = FileNotFoundError()
    mock_config_path.return_value = mock_path

    result = _load_config_dict()
    assert result == {}


@patch("autoscrapper.config.config_path")
def test_load_config_dict_json_decode_error(mock_config_path):
    """Test that _load_config_dict returns an empty dict if the file contains invalid JSON."""
    mock_path = MagicMock(spec=Path)
    mock_path.read_bytes.return_value = b"invalid json"
    mock_config_path.return_value = mock_path

    # orjson.loads will raise JSONDecodeError
    result = _load_config_dict()
    assert result == {}


@patch("autoscrapper.config.config_path")
def test_load_config_dict_os_error(mock_config_path):
    """Test that _load_config_dict returns an empty dict if an OSError occurs."""
    mock_path = MagicMock(spec=Path)
    mock_path.read_bytes.side_effect = OSError("Read error")
    mock_config_path.return_value = mock_path

    result = _load_config_dict()
    assert result == {}


@patch("autoscrapper.config.config_path")
def test_load_config_dict_not_a_dict(mock_config_path):
    """Test that _load_config_dict returns an empty dict if the JSON is not a dictionary."""
    mock_path = MagicMock(spec=Path)
    mock_path.read_bytes.return_value = b"[1, 2, 3]"
    mock_config_path.return_value = mock_path

    result = _load_config_dict()
    assert result == {}


@patch("autoscrapper.config.config_path")
def test_load_config_dict_success(mock_config_path):
    """Test that _load_config_dict returns the loaded dictionary and applies migrations."""
    # Use an older version to verify migration is applied
    payload = {"version": 1, "scan": {"debug_ocr": True}}
    mock_path = MagicMock(spec=Path)
    mock_path.read_bytes.return_value = json.dumps(payload).encode()
    mock_config_path.return_value = mock_path

    result = _load_config_dict()
    assert result["version"] == CONFIG_VERSION
    assert result["scan"]["debug_ocr"] is True
