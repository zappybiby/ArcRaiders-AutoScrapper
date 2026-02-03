from __future__ import annotations

import sys
import time
from typing import Optional

from .keybinds import DEFAULT_STOP_KEY, normalize_stop_key

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    import pydirectinput as _pydirectinput

    _pydirectinput.FAILSAFE = False
    _pydirectinput.PAUSE = 0

    _USER32 = ctypes.WinDLL("user32", use_last_error=True)
    _GetAsyncKeyState = _USER32.GetAsyncKeyState
    _GetAsyncKeyState.argtypes = [wintypes.INT]
    _GetAsyncKeyState.restype = wintypes.SHORT

    _VkKeyScanW = _USER32.VkKeyScanW
    _VkKeyScanW.argtypes = [wintypes.WCHAR]
    _VkKeyScanW.restype = wintypes.SHORT

    _SPECIAL_VK: dict[str, int] = {
        "escape": 0x1B,
        "enter": 0x0D,
        "space": 0x20,
        "tab": 0x09,
        "backspace": 0x08,
        "delete": 0x2E,
        "insert": 0x2D,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
    }

    def _vk_code_for_stop_key(stop_key: str) -> Optional[int]:
        key = normalize_stop_key(stop_key)
        special = _SPECIAL_VK.get(key)
        if special is not None:
            return special
        if key.startswith("f") and key[1:].isdigit():
            number = int(key[1:])
            if 1 <= number <= 12:
                return 0x70 + (number - 1)
        if len(key) == 1:
            if key.isalpha() or key.isdigit():
                return ord(key.upper())
            vk_scan = int(_VkKeyScanW(key))
            if vk_scan == -1:
                return None
            return vk_scan & 0xFF
        return None

    def key_pressed(stop_key: str = DEFAULT_STOP_KEY) -> bool:
        vk = _vk_code_for_stop_key(stop_key)
        if vk is None:
            vk = _SPECIAL_VK["escape"]
        state = _GetAsyncKeyState(vk)
        return bool(state & 0x8000) or bool(state & 0x0001)

    def escape_pressed() -> bool:
        return key_pressed("escape")

    def moveTo(x: int, y: int, duration: float = 0.0) -> None:
        _pydirectinput.moveTo(int(x), int(y), duration=duration)

    def leftClick(x: int, y: int) -> None:
        _pydirectinput.click(x=int(x), y=int(y), button="left")

    def rightClick(x: int, y: int) -> None:
        _pydirectinput.click(x=int(x), y=int(y), button="right")

    def vscroll(clicks: int, interval: float = 0.0) -> None:
        if clicks == 0:
            return
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            _pydirectinput.scroll(step)
            if interval > 0:
                time.sleep(interval)

elif sys.platform.startswith("linux"):
    import threading

    from pynput import keyboard, mouse

    _MOUSE = mouse.Controller()
    _KEY_STATE: set[object] = set()
    _KEY_LATCH: set[str] = set()
    _LISTENER: Optional[keyboard.Listener] = None
    _LISTENER_LOCK = threading.Lock()
    _KEY_STATE_LOCK = threading.Lock()

    _SPECIAL_KEYS: dict[object, str] = {}

    def _register_special_key(attr: str, canonical: str) -> None:
        key_obj = getattr(keyboard.Key, attr, None)
        if key_obj is not None:
            _SPECIAL_KEYS[key_obj] = canonical

    for _attr, _canonical in (
        ("esc", "escape"),
        ("enter", "enter"),
        ("space", "space"),
        ("tab", "tab"),
        ("backspace", "backspace"),
        ("delete", "delete"),
        ("insert", "insert"),
        ("home", "home"),
        ("end", "end"),
        ("page_up", "pageup"),
        ("page_down", "pagedown"),
        ("up", "up"),
        ("down", "down"),
        ("left", "left"),
        ("right", "right"),
        ("f1", "f1"),
        ("f2", "f2"),
        ("f3", "f3"),
        ("f4", "f4"),
        ("f5", "f5"),
        ("f6", "f6"),
        ("f7", "f7"),
        ("f8", "f8"),
        ("f9", "f9"),
        ("f10", "f10"),
        ("f11", "f11"),
        ("f12", "f12"),
    ):
        _register_special_key(_attr, _canonical)

    def _canonical_linux_key(key: object) -> Optional[str]:
        special = _SPECIAL_KEYS.get(key)
        if special is not None:
            return special
        if isinstance(key, keyboard.KeyCode) and key.char:
            return normalize_stop_key(key.char)
        return None

    def _ensure_key_listener() -> None:
        global _LISTENER
        if _LISTENER is not None:
            return
        with _LISTENER_LOCK:
            if _LISTENER is not None:
                return

            def on_press(key) -> None:
                canonical = _canonical_linux_key(key)
                with _KEY_STATE_LOCK:
                    _KEY_STATE.add(key)
                    if canonical:
                        _KEY_LATCH.add(canonical)

            def on_release(key) -> None:
                with _KEY_STATE_LOCK:
                    _KEY_STATE.discard(key)

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            _LISTENER = listener

    def key_pressed(stop_key: str = DEFAULT_STOP_KEY) -> bool:
        _ensure_key_listener()
        canonical_target = normalize_stop_key(stop_key)
        with _KEY_STATE_LOCK:
            for active in _KEY_STATE:
                if _canonical_linux_key(active) == canonical_target:
                    return True
            if canonical_target in _KEY_LATCH:
                _KEY_LATCH.discard(canonical_target)
                return True
            return False

    def escape_pressed() -> bool:
        return key_pressed("escape")

    def moveTo(x: int, y: int, duration: float = 0.0) -> None:
        x = int(x)
        y = int(y)
        if duration <= 0:
            _MOUSE.position = (x, y)
            return

        start_x, start_y = _MOUSE.position
        steps = max(1, int(duration / 0.01))
        sleep_time = duration / steps
        for i in range(1, steps + 1):
            nx = start_x + (x - start_x) * (i / steps)
            ny = start_y + (y - start_y) * (i / steps)
            _MOUSE.position = (int(nx), int(ny))
            time.sleep(sleep_time)

    def leftClick(x: int, y: int) -> None:
        _MOUSE.position = (int(x), int(y))
        _MOUSE.click(mouse.Button.left, 1)

    def rightClick(x: int, y: int) -> None:
        _MOUSE.position = (int(x), int(y))
        _MOUSE.click(mouse.Button.right, 1)

    def vscroll(clicks: int, interval: float = 0.0) -> None:
        if clicks == 0:
            return
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            _MOUSE.scroll(0, step)
            if interval > 0:
                time.sleep(interval)

else:
    raise RuntimeError(f"Unsupported platform for input driver: {sys.platform}")
