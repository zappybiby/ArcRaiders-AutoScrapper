from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import mss
import numpy as np
import pywinctl as pwc

from .inventory_grid import Cell
from . import input_driver as pdi
from .keybinds import DEFAULT_STOP_KEY


# Target window
def _default_target_app() -> str:
    if sys.platform.startswith("linux"):
        return "Arc Raiders"
    return "PioneerGame.exe"


TARGET_APP = os.environ.get("AUTOSCRAPPER_TARGET_APP") or _default_target_app()
WINDOW_TIMEOUT = 30.0
WINDOW_POLL_INTERVAL = 0.05

# Click pacing
ACTION_DELAY = 0.05
MOVE_DURATION = 0.05
CELL_INFOBOX_LEFT_RIGHT_CLICK_GAP = 0.25
SELL_RECYCLE_SPEED_MULT = (
    1.5  # extra slack vs default pacing (MOVE_DURATION/ACTION_DELAY)
)
SELL_RECYCLE_MOVE_DURATION = MOVE_DURATION * SELL_RECYCLE_SPEED_MULT
SELL_RECYCLE_ACTION_DELAY = ACTION_DELAY * SELL_RECYCLE_SPEED_MULT
SELL_RECYCLE_POST_DELAY = 0.1  # seconds to allow item collapse after confirm

# Scrolling
# Pattern derivation (calibrator data):
# - dy_per_scroll_px ~= 31.961 at 1920x1080
# - row_height_px ~= 104.000, so rows_per_scroll ~= 0.3073
# - target move per page is 5 rows (520 px)
# The sequence below is the 20-step minimum-error pattern while allowing up to
# 10 px of undershoot (old-row overlap) and is used as a repeating cycle.
# Calibration at multiple resolutions was consistent with the same rows/scroll
# ratio, so this fixed pattern is used across resolutions.
SCROLL_CLICKS_PATTERN = (
    16,
    17,
    16,
    16,
    17,
    16,
    16,
    16,
    17,
    16,
    16,
    16,
    17,
    16,
    16,
    17,
    16,
    16,
    16,
    17,
)
SCROLL_MOVE_DURATION = 0.5
SCROLL_INTERVAL = 0.04
SCROLL_SETTLE_DELAY = 0.05

_MSS_LOCAL = threading.local()


@dataclass(frozen=True)
class WindowSnapshot:
    win_left: int
    win_top: int
    win_width: int
    win_height: int
    work_area: Tuple[int, int, int, int]
    mon_left: int
    mon_top: int
    mon_right: int
    mon_bottom: int


def get_active_target_window(target_app: str = TARGET_APP) -> Optional[pwc.Window]:
    """
    Return the active window if it matches the target app; otherwise None.
    """
    win = pwc.getActiveWindow()
    if win is None:
        return None
    target_lower = target_app.lower()
    app = (win.getAppName() or "").lower()
    title = ""
    if hasattr(win, "title"):
        title = getattr(win, "title") or ""
    if not title and hasattr(win, "getTitle"):
        try:
            title = win.getTitle() or ""
        except Exception:
            title = ""
    title_lower = title.lower()
    if target_lower in app or (title_lower and target_lower in title_lower):
        return win
    return None


def build_window_snapshot(win: pwc.Window) -> WindowSnapshot:
    """
    Capture window bounds and display metadata for the current target window.
    """
    _display_name, _display_size, work_area = window_display_info(win)
    mon_left, mon_top, mon_right, mon_bottom = window_monitor_rect(win)
    win_left, win_top, win_width, win_height = window_rect(win)
    return WindowSnapshot(
        win_left=win_left,
        win_top=win_top,
        win_width=win_width,
        win_height=win_height,
        work_area=work_area,
        mon_left=mon_left,
        mon_top=mon_top,
        mon_right=mon_right,
        mon_bottom=mon_bottom,
    )


def stop_key_pressed(stop_key: str = DEFAULT_STOP_KEY) -> bool:
    """
    Detect whether the configured stop key is currently pressed.
    """
    return pdi.key_pressed(stop_key)


def abort_if_escape_pressed(stop_key: str = DEFAULT_STOP_KEY) -> None:
    """
    Raise KeyboardInterrupt if the configured stop key is down.
    """
    if stop_key_pressed(stop_key):
        raise KeyboardInterrupt(f"{stop_key} pressed")


def wait_for_target_window(
    target_app: str = TARGET_APP,
    timeout: float = WINDOW_TIMEOUT,
    poll_interval: float = WINDOW_POLL_INTERVAL,
    stop_key: str = DEFAULT_STOP_KEY,
) -> pwc.Window:
    """
    Wait until the active window belongs to the target process.
    """
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        abort_if_escape_pressed(stop_key)
        win = get_active_target_window(target_app=target_app)
        if win is not None:
            return win
        sleep_with_abort(poll_interval, stop_key=stop_key)

    raise TimeoutError(f"Timed out waiting for active window {target_app!r}")


def window_rect(win: pwc.Window) -> Tuple[int, int, int, int]:
    """
    (left, top, width, height) in screen coordinates for the window.
    """
    return int(win.left), int(win.top), int(win.width), int(win.height)


def window_display_info(
    win: pwc.Window,
) -> Tuple[str, Tuple[int, int], Tuple[int, int, int, int]]:
    """
    Return (display name, display size, work area) and enforce that the window is on a single monitor.
    """
    display_names = win.getDisplay()
    if not display_names:
        raise RuntimeError("Unable to determine which monitor the target window is on.")
    if len(display_names) > 1:
        joined = ", ".join(display_names)
        raise RuntimeError(
            f"Target window spans multiple monitors ({joined}); move it fully onto one display."
        )

    display_name = display_names[0]
    size = pwc.getScreenSize(display_name)
    work_area = pwc.getWorkArea(display_name)
    return display_name, size, work_area


def window_monitor_rect(win: pwc.Window) -> Tuple[int, int, int, int]:
    """
    Return (left, top, right, bottom) bounds for the physical monitor containing
    the window center.

    This differs from the OS "work area", which excludes taskbars/docks and can
    cause false warnings for borderless fullscreen windows.
    """
    win_left, win_top, win_width, win_height = window_rect(win)
    center_x = win_left + (win_width // 2)
    center_y = win_top + (win_height // 2)

    sct = _get_mss()
    monitors = getattr(sct, "monitors", None)
    if not monitors or len(monitors) < 2:
        raise RuntimeError("Unable to determine monitor bounds via mss.")

    # Index 0 is the "all monitors" virtual rectangle.
    for mon in monitors[1:]:
        mon_left = int(mon["left"])
        mon_top = int(mon["top"])
        mon_right = mon_left + int(mon["width"])
        mon_bottom = mon_top + int(mon["height"])
        if mon_left <= center_x < mon_right and mon_top <= center_y < mon_bottom:
            return mon_left, mon_top, mon_right, mon_bottom

    raise RuntimeError("Unable to map target window to a monitor via mss.")


def _get_mss() -> "MSSBase":
    """
    Lazily create a thread-local MSS instance for screen capture.

    MSS stores platform capture handles in thread-local storage internally.
    Reusing one MSS instance across threads on Windows can fail with errors like
    missing `srcdc`, so each thread keeps its own instance.
    """
    if sys.platform not in ("win32", "linux"):
        raise RuntimeError(
            "Screen capture requires Windows or Linux; this build targets X11/XWayland."
        )

    sct = getattr(_MSS_LOCAL, "instance", None)
    if sct is None:
        sct = mss.mss()
        _MSS_LOCAL.instance = sct
    return sct


def _reset_mss() -> None:
    """
    Drop the current thread-local MSS instance so the next capture recreates it.
    """
    sct = getattr(_MSS_LOCAL, "instance", None)
    if sct is None:
        return

    close = getattr(sct, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
    _MSS_LOCAL.instance = None


def _is_mss_thread_handle_error(exc: Exception) -> bool:
    """
    Detect stale-thread-handle MSS failures that can recover by recreating MSS.
    """
    text = str(exc).lower()
    return "srcdc" in text or "thread._local" in text


def capture_region(region: Tuple[int, int, int, int]) -> np.ndarray:
    """
    Capture a BGR screenshot of the given region (left, top, width, height).
    """
    left, top, width, height = region
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid capture region size: width={width}, height={height}")

    sct = _get_mss()
    bbox = {
        "left": int(left),
        "top": int(top),
        "width": int(width),
        "height": int(height),
    }

    try:
        shot = sct.grab(bbox)
    except Exception as exc:
        if _is_mss_thread_handle_error(exc):
            _reset_mss()
            try:
                shot = _get_mss().grab(bbox)
            except Exception as retry_exc:
                raise RuntimeError(
                    f"mss failed to capture the requested region {bbox}: {retry_exc}"
                ) from retry_exc
        else:
            raise RuntimeError(
                f"mss failed to capture the requested region {bbox}: {exc}"
            ) from exc

    frame = np.asarray(shot)
    if frame.shape[2] == 4:
        frame = frame[:, :, :3]  # drop alpha, keep BGR order
    return np.ascontiguousarray(frame)


def sleep_with_abort(duration: float, *, stop_key: str = DEFAULT_STOP_KEY) -> None:
    """
    Sleep for a specific duration and honor configured abort key presses.
    """
    time.sleep(duration)
    abort_if_escape_pressed(stop_key)


def pause_action(
    duration: float = ACTION_DELAY, *, stop_key: str = DEFAULT_STOP_KEY
) -> None:
    """
    Standard pause to keep a safe delay between input/processing steps.
    """
    sleep_with_abort(duration, stop_key=stop_key)


def timed_action(func, *args, stop_key: str = DEFAULT_STOP_KEY, **kwargs) -> None:
    """
    Run an input action while checking for configured abort key presses.
    """
    abort_if_escape_pressed(stop_key)
    func(*args, **kwargs)


def click_absolute(
    x: int,
    y: int,
    pause: float = ACTION_DELAY,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
) -> None:
    timed_action(pdi.leftClick, x, y, stop_key=stop_key)
    pause_action(pause, stop_key=stop_key)


def click_window_relative(
    x: int,
    y: int,
    window_left: int,
    window_top: int,
    pause: float = ACTION_DELAY,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
) -> None:
    click_absolute(
        int(window_left + x), int(window_top + y), pause=pause, stop_key=stop_key
    )


def move_absolute(
    x: int,
    y: int,
    duration: float = MOVE_DURATION,
    pause: float = ACTION_DELAY,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
) -> None:
    timed_action(pdi.moveTo, x, y, duration=duration, stop_key=stop_key)
    pause_action(pause, stop_key=stop_key)


def move_window_relative(
    x: int,
    y: int,
    window_left: int,
    window_top: int,
    duration: float = MOVE_DURATION,
    pause: float = ACTION_DELAY,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
) -> None:
    move_absolute(
        int(window_left + x),
        int(window_top + y),
        duration=duration,
        pause=pause,
        stop_key=stop_key,
    )


def open_cell_item_infobox(
    cell: Cell,
    window_left: int,
    window_top: int,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
    pause: float = ACTION_DELAY,
    move_duration: float = MOVE_DURATION,
    left_right_click_gap: float = CELL_INFOBOX_LEFT_RIGHT_CLICK_GAP,
) -> None:
    """
    Hover the cell, then left-click and right-click to open its item infobox.
    """
    abort_if_escape_pressed(stop_key)
    cx, cy = _cell_screen_center(cell, window_left, window_top)
    timed_action(pdi.moveTo, cx, cy, duration=move_duration, stop_key=stop_key)
    pause_action(pause, stop_key=stop_key)
    timed_action(pdi.leftClick, cx, cy, stop_key=stop_key)
    pause_action(left_right_click_gap, stop_key=stop_key)
    timed_action(pdi.rightClick, cx, cy, stop_key=stop_key)
    pause_action(pause, stop_key=stop_key)


def scroll_to_next_grid_at(
    clicks: int,
    grid_center_abs: Tuple[int, int],
    safe_point_abs: Optional[Tuple[int, int]] = None,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
    pause: float = ACTION_DELAY,
    move_duration: float = SCROLL_MOVE_DURATION,
    scroll_interval: float = SCROLL_INTERVAL,
    settle_delay: float = SCROLL_SETTLE_DELAY,
) -> None:
    """
    Scroll with the cursor positioned inside the grid to ensure the carousel moves.
    Optionally park the cursor back at a safe point afterwards.
    """
    abort_if_escape_pressed(stop_key)
    gx, gy = grid_center_abs
    scroll_clicks = -abs(clicks)

    # Match the working standalone script: slow move into position, click, then vertical scroll.
    timed_action(pdi.moveTo, gx, gy, duration=move_duration, stop_key=stop_key)
    pause_action(pause, stop_key=stop_key)
    abort_if_escape_pressed(stop_key)
    timed_action(pdi.leftClick, gx, gy, stop_key=stop_key)
    pause_action(pause, stop_key=stop_key)

    print(
        f"[scroll] vscroll clicks={scroll_clicks} interval={scroll_interval} at=({gx},{gy})",
        flush=True,
    )
    timed_action(
        pdi.vscroll, clicks=scroll_clicks, interval=scroll_interval, stop_key=stop_key
    )
    sleep_with_abort(settle_delay, stop_key=stop_key)

    if safe_point_abs is not None:
        sx, sy = safe_point_abs
        move_absolute(sx, sy, pause=pause, stop_key=stop_key)


def _cell_screen_center(
    cell: Cell, window_left: int, window_top: int
) -> Tuple[int, int]:
    cx, cy = cell.safe_center
    return int(window_left + cx), int(window_top + cy)
