from __future__ import annotations

import sys
import time
from typing import Optional

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
        return bool(_GetAsyncKeyState(_VK_ESCAPE) & 0x8000)

    def moveTo(x: int, y: int, duration: float = 0.0, _pause: bool = True) -> None:
        _pydirectinput.moveTo(x, y, duration=duration)

    def leftClick(x: int, y: int, _pause: bool = True) -> None:
        _pydirectinput.click(x=x, y=y, button="left")

    def rightClick(x: int, y: int, _pause: bool = True) -> None:
        _pydirectinput.click(x=x, y=y, button="right")

    def vscroll(clicks: int, interval: float = 0.0, _pause: bool = True) -> None:
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

            def on_release(key) -> None:
                _KEY_STATE.discard(key)

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            _LISTENER = listener

    def escape_pressed() -> bool:
        _ensure_key_listener()
        return keyboard.Key.esc in _KEY_STATE

    def moveTo(x: int, y: int, duration: float = 0.0, _pause: bool = True) -> None:
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

    def leftClick(x: int, y: int, _pause: bool = True) -> None:
        _MOUSE.position = (x, y)
        _MOUSE.click(mouse.Button.left, 1)

    def rightClick(x: int, y: int, _pause: bool = True) -> None:
        _MOUSE.position = (x, y)
        _MOUSE.click(mouse.Button.right, 1)

    def vscroll(clicks: int, interval: float = 0.0, _pause: bool = True) -> None:
        if clicks == 0:
            return
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            _MOUSE.scroll(0, step)
            if interval > 0:
                time.sleep(interval)

else:
    raise RuntimeError(f"Unsupported platform for input driver: {sys.platform}")
