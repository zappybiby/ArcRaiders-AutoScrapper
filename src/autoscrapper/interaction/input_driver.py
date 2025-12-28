from __future__ import annotations

import sys
import time
from typing import Optional

PAUSE = 0.0


def _maybe_pause(pause: bool) -> None:
    if pause and PAUSE > 0:
        time.sleep(PAUSE)


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

    _VK_ESCAPE = 0x1B

    def escape_pressed() -> bool:
        state = _GetAsyncKeyState(_VK_ESCAPE)
        return bool(state & 0x8000) or bool(state & 0x0001)

    def moveTo(x: int, y: int, duration: float = 0.0, _pause: bool = True) -> None:
        _pydirectinput.moveTo(int(x), int(y), duration=duration)
        _maybe_pause(_pause)

    def leftClick(x: int, y: int, _pause: bool = True) -> None:
        _pydirectinput.click(x=int(x), y=int(y), button="left")
        _maybe_pause(_pause)

    def rightClick(x: int, y: int, _pause: bool = True) -> None:
        _pydirectinput.click(x=int(x), y=int(y), button="right")
        _maybe_pause(_pause)

    def vscroll(clicks: int, interval: float = 0.0, _pause: bool = True) -> None:
        if clicks == 0:
            return
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            _pydirectinput.scroll(step)
            if interval > 0:
                time.sleep(interval)
        _maybe_pause(_pause)

elif sys.platform.startswith("linux"):
    import threading

    from pynput import keyboard, mouse

    _MOUSE = mouse.Controller()
    _KEY_STATE: set[object] = set()
    _ESCAPE_PRESSED = threading.Event()
    _LISTENER: Optional[keyboard.Listener] = None
    _LISTENER_LOCK = threading.Lock()

    def _ensure_key_listener() -> None:
        global _LISTENER
        if _LISTENER is not None:
            return
        with _LISTENER_LOCK:
            if _LISTENER is not None:
                return

            def on_press(key) -> None:
                _KEY_STATE.add(key)
                if key == keyboard.Key.esc:
                    _ESCAPE_PRESSED.set()

            def on_release(key) -> None:
                _KEY_STATE.discard(key)

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            _LISTENER = listener

    def escape_pressed() -> bool:
        _ensure_key_listener()
        if keyboard.Key.esc in _KEY_STATE:
            return True
        if _ESCAPE_PRESSED.is_set():
            _ESCAPE_PRESSED.clear()
            return True
        return False

    def moveTo(x: int, y: int, duration: float = 0.0, _pause: bool = True) -> None:
        x = int(x)
        y = int(y)
        if duration <= 0:
            _MOUSE.position = (x, y)
            _maybe_pause(_pause)
            return

        start_x, start_y = _MOUSE.position
        steps = max(1, int(duration / 0.01))
        sleep_time = duration / steps
        for i in range(1, steps + 1):
            nx = start_x + (x - start_x) * (i / steps)
            ny = start_y + (y - start_y) * (i / steps)
            _MOUSE.position = (int(nx), int(ny))
            time.sleep(sleep_time)
        _maybe_pause(_pause)

    def leftClick(x: int, y: int, _pause: bool = True) -> None:
        _MOUSE.position = (int(x), int(y))
        _MOUSE.click(mouse.Button.left, 1)
        _maybe_pause(_pause)

    def rightClick(x: int, y: int, _pause: bool = True) -> None:
        _MOUSE.position = (int(x), int(y))
        _MOUSE.click(mouse.Button.right, 1)
        _maybe_pause(_pause)

    def vscroll(clicks: int, interval: float = 0.0, _pause: bool = True) -> None:
        if clicks == 0:
            return
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            _MOUSE.scroll(0, step)
            if interval > 0:
                time.sleep(interval)
        _maybe_pause(_pause)

else:
    raise RuntimeError(f"Unsupported platform for input driver: {sys.platform}")
