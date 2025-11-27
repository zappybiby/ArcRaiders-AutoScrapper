from __future__ import annotations

import ctypes
import time
from typing import Optional, Tuple

import cv2
import numpy as np
import pywinctl as pwc
import pydirectinput as pdi

try:
    import mss  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    mss = None

try:
    import pyautogui  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pyautogui = None

from grid_navigation import Cell, Grid

# Target window
TARGET_APP = "PioneerGame.exe"
WINDOW_TIMEOUT = 30.0
WINDOW_POLL_INTERVAL = 0.05

# Click pacing
ACTION_DELAY = 0.05
MOVE_DURATION = 0.05
SELL_RECYCLE_SPEED_MULT = 1.5  # extra slack vs default pacing (MOVE_DURATION/ACTION_DELAY)
SELL_RECYCLE_MOVE_DURATION = MOVE_DURATION * SELL_RECYCLE_SPEED_MULT
SELL_RECYCLE_ACTION_DELAY = ACTION_DELAY * SELL_RECYCLE_SPEED_MULT

# Cell click positioning
LAST_ROW_SAFE_Y_RATIO = 0.85

# Scrolling
# Alternate 19/20 downward scroll clicks to advance between 6x4 grids.
SCROLL_CLICKS_PER_PAGE = 19
SCROLL_INTERVAL = 0.0
SCROLL_SETTLE_DELAY = 0.05

# Keyboard
VK_ESCAPE = 0x1B

# Optional user32 handle for escape detection (Windows only)
try:
    _USER32 = ctypes.windll.user32  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - platform dependent
    _USER32 = None


def escape_pressed() -> bool:
    """
    Detect whether Escape is currently pressed (Windows).
    """
    if _USER32 is None:
        return False
    return bool(_USER32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def abort_if_escape_pressed() -> None:
    """
    Raise KeyboardInterrupt if Escape is down.
    """
    if escape_pressed():
        raise KeyboardInterrupt("Escape pressed")


def wait_for_target_window(
    target_app: str = TARGET_APP,
    timeout: float = WINDOW_TIMEOUT,
    poll_interval: float = WINDOW_POLL_INTERVAL,
) -> pwc.Window:
    """
    Wait until the active window belongs to the target process.
    """
    start = time.monotonic()
    target_lower = target_app.lower()

    while time.monotonic() - start < timeout:
        abort_if_escape_pressed()
        win = pwc.getActiveWindow()
        if win is not None:
            app = (win.getAppName() or "").lower()
            if app == target_lower:
                return win
        time.sleep(poll_interval)

    raise TimeoutError(f"Timed out waiting for active window {target_app!r}")


def window_rect(win: pwc.Window) -> Tuple[int, int, int, int]:
    """
    (left, top, width, height) in screen coordinates for the window.
    """
    return int(win.left), int(win.top), int(win.width), int(win.height)


def _capture_with_mss(region: Tuple[int, int, int, int]) -> np.ndarray:
    left, top, width, height = region
    with mss.mss() as sct:
        raw = np.array(
            sct.grab(
                {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                }
            )
        )
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)


def _capture_with_pyautogui(region: Tuple[int, int, int, int]) -> np.ndarray:
    left, top, width, height = region
    img = pyautogui.screenshot(region=(left, top, width, height))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def capture_region(region: Tuple[int, int, int, int]) -> np.ndarray:
    """
    Capture a BGR screenshot of the given region (left, top, width, height).
    """
    if mss is not None:
        return _capture_with_mss(region)
    if pyautogui is not None:
        return _capture_with_pyautogui(region)
    raise RuntimeError("Install either 'mss' or 'pyautogui' for screenshots")


def sleep_with_abort(duration: float) -> None:
    """
    Sleep for a specific duration and honor Escape aborts.
    """
    time.sleep(duration)
    abort_if_escape_pressed()


def pause_action(duration: float = ACTION_DELAY) -> None:
    """
    Standard pause to keep a safe delay between input/processing steps.
    """
    sleep_with_abort(duration)


def timed_action(label: str, func, *args, **kwargs) -> None:
    """
    Run an input action while checking for Escape.
    """
    abort_if_escape_pressed()
    func(*args, **kwargs)


def click_absolute(x: int, y: int, label: str = "click", pause: float = ACTION_DELAY) -> None:
    timed_action(label, pdi.leftClick, x, y, _pause=False)
    pause_action(pause)


def click_window_relative(
    x: int,
    y: int,
    window_left: int,
    window_top: int,
    label: str = "click",
    pause: float = ACTION_DELAY,
) -> None:
    click_absolute(int(window_left + x), int(window_top + y), label, pause=pause)


def move_absolute(
    x: int,
    y: int,
    label: str = "move",
    duration: float = MOVE_DURATION,
    pause: float = ACTION_DELAY,
) -> None:
    timed_action(f"{label} moveTo", pdi.moveTo, x, y, duration=duration)
    pause_action(pause)


def move_window_relative(
    x: int,
    y: int,
    window_left: int,
    window_top: int,
    label: str = "move",
    duration: float = MOVE_DURATION,
    pause: float = ACTION_DELAY,
) -> None:
    move_absolute(int(window_left + x), int(window_top + y), label, duration=duration, pause=pause)


def open_cell_menu(cell: Cell, window_left: int, window_top: int) -> None:
    """
    Hover the cell, then left-click and right-click to open its context menu.
    """
    abort_if_escape_pressed()
    cx, cy = _cell_screen_center(cell, window_left, window_top)
    timed_action("moveTo", pdi.moveTo, cx, cy, duration=MOVE_DURATION)
    pause_action()
    timed_action("leftClick", pdi.leftClick, cx, cy, _pause=False)
    pause_action()
    timed_action("rightClick", pdi.rightClick, cx, cy, _pause=False)
    pause_action()


def scroll_to_next_grid(scroll_clicks_per_page: int = SCROLL_CLICKS_PER_PAGE) -> None:
    """
    Scroll quickly to reveal the next 6x4 grid of items.
    """
    raise RuntimeError(
        "scroll_to_next_grid now requires explicit grid/safe coordinates. "
        "Use scroll_to_next_grid_at instead."
    )


def scroll_to_next_grid_at(
    clicks: int,
    grid_center_abs: Tuple[int, int],
    safe_point_abs: Optional[Tuple[int, int]] = None,
) -> None:
    """
    Scroll with the cursor positioned inside the grid to ensure the carousel moves.
    Optionally park the cursor back at a safe point afterwards.
    """
    abort_if_escape_pressed()
    gx, gy = grid_center_abs
    move_absolute(gx, gy, label="move to grid center before scroll")

    scroll_clicks = -abs(clicks)
    timed_action("scroll", pdi.scroll, scroll_clicks, _pause=False, interval=SCROLL_INTERVAL)
    sleep_with_abort(SCROLL_SETTLE_DELAY)

    if safe_point_abs is not None:
        sx, sy = safe_point_abs
        move_absolute(sx, sy, label="move to safe area after scroll")


def _cell_screen_center(cell: Cell, window_left: int, window_top: int) -> Tuple[int, int]:
    cx, cy = cell.safe_center
    # Game quirk: on the last row the infobox can render off-screen when we click dead-center,
    # hiding Sell/Recycle. Bias toward the bottom of the safe area to keep the infobox visible.
    if cell.row == Grid.ROWS - 1:
        x1, y1, x2, y2 = cell.safe_bounds
        safe_height = y2 - y1
        cy = y1 + safe_height * LAST_ROW_SAFE_Y_RATIO
    return int(window_left + cx), int(window_top + cy)
