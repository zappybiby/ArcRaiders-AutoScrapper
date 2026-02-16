from __future__ import annotations

import re
from typing import Optional

DEFAULT_STOP_KEY = "escape"

_ALIAS_TO_CANONICAL = {
    "esc": "escape",
    "escape": "escape",
    "return": "enter",
    "enter": "enter",
    "spacebar": "space",
    "space": "space",
    "tab": "tab",
    "backspace": "backspace",
    "del": "delete",
    "delete": "delete",
    "ins": "insert",
    "insert": "insert",
    "home": "home",
    "end": "end",
    "pgup": "pageup",
    "pageup": "pageup",
    "page_up": "pageup",
    "pgdn": "pagedown",
    "pagedown": "pagedown",
    "page_down": "pagedown",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}

_MODIFIER_KEYS = {
    "shift",
    "ctrl",
    "control",
    "alt",
    "meta",
    "super",
    "command",
}

_CANONICAL_DISPLAY = {
    "escape": "Esc",
    "enter": "Enter",
    "space": "Space",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Page Up",
    "pagedown": "Page Down",
    "up": "Up Arrow",
    "down": "Down Arrow",
    "left": "Left Arrow",
    "right": "Right Arrow",
}

_FUNCTION_KEY_PATTERN = re.compile(r"^f([1-9]|1[0-2])$")


def normalize_stop_key(value: object) -> str:
    """
    Normalize user/config input into a canonical stop-key name.
    """
    if not isinstance(value, str):
        return DEFAULT_STOP_KEY

    raw = value.strip()
    if not raw:
        return DEFAULT_STOP_KEY

    lowered = raw.lower()
    alias = _ALIAS_TO_CANONICAL.get(lowered)
    if alias is not None:
        return alias

    if _FUNCTION_KEY_PATTERN.match(lowered):
        return lowered

    if len(raw) == 1 and raw.isprintable() and not raw.isspace():
        return lowered if raw.isalpha() else raw

    return DEFAULT_STOP_KEY


def stop_key_label(key: object) -> str:
    canonical = normalize_stop_key(key)
    display = _CANONICAL_DISPLAY.get(canonical)
    if display is not None:
        return display
    if _FUNCTION_KEY_PATTERN.match(canonical):
        return canonical.upper()
    if len(canonical) == 1:
        return canonical.upper() if canonical.isalpha() else canonical
    return canonical


def textual_key_to_stop_key(key: str, character: Optional[str] = None) -> Optional[str]:
    """
    Convert a Textual key event payload into a canonical stop-key name.
    Returns None for modifier-only presses that should be ignored.
    """
    lowered = key.lower().strip()
    if lowered in _MODIFIER_KEYS:
        return None

    alias = _ALIAS_TO_CANONICAL.get(lowered)
    if alias is not None:
        return alias

    if _FUNCTION_KEY_PATTERN.match(lowered):
        return lowered

    if character and len(character) == 1 and character.isprintable():
        if character.isspace():
            return "space"
        return normalize_stop_key(character)

    if len(lowered) == 1 and lowered.isprintable() and not lowered.isspace():
        return normalize_stop_key(lowered)

    return None
