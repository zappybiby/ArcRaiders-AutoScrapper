"""Window lookup and capture for games running through XWayland."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import time
from contextlib import ExitStack, closing, contextmanager
from contextvars import ContextVar

import cairocffi as cairo
import numpy as np
import xcffib.xproto
from Xlib import X, Xatom, display, error


def mouse_control_preauthorized() -> bool:
    if "kde" not in os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":"):
        return False
    read = ["kreadconfig6", "--file", "kwinrc", "--group", "Xwayland", "--key"]
    try:
        allowed = subprocess.run(
            [*read, "XwaylandEisNoPrompt", "--type", "bool"],
            capture_output=True,
            timeout=1,
        )
        if allowed.returncode == 0:
            return True
        apps = subprocess.check_output(
            [*read, "XwaylandEisNoPromptApps"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
        )
    except OSError, subprocess.SubprocessError:
        return False
    # XWayland identifies its input client by the basename of argv[0].
    names = next(
        csv.reader([apps.rstrip("\n")], escapechar="\\", quoting=csv.QUOTE_NONE)
    )
    return os.path.basename(sys.orig_argv[0]) in names


def _active_id(root, atom) -> int:
    prop = root.get_full_property(atom, Xatom.WINDOW)
    return int(prop.value[0]) if prop is not None and len(prop.value) else 0


def active_target(name: str) -> int | None:
    with closing(display.Display()) as connection:
        root = connection.screen().root
        xid = _active_id(root, connection.intern_atom("_NET_ACTIVE_WINDOW"))
        if not xid:
            return None
        window = connection.create_resource_object("window", xid)
        try:
            title = window.get_full_property(
                connection.intern_atom("_NET_WM_NAME"), X.AnyPropertyType
            )
            label = (
                title.value.decode("utf-8", "replace")
                if title
                else window.get_wm_name()
            )
            labels = (label or "", *(window.get_wm_class() or ()))
        except error.BadWindow:
            return None
        if any(name.casefold() in label.casefold() for label in labels):
            return window.id
        return None


def _bounds(root, window) -> tuple[int, int, int, int]:
    geometry = window.get_geometry()
    origin = root.translate_coords(window, 0, 0)
    return (origin.x, origin.y, geometry.width, geometry.height)


def window_geometry(xid: int):
    with closing(display.Display()) as connection:
        root = connection.screen().root
        window = connection.create_resource_object("window", xid)
        left, top, width, height = _bounds(root, window)
        monitors = {
            (m.x, m.y, m.x + m.width_in_pixels, m.y + m.height_in_pixels)
            for m in root.xrandr_get_monitors(True).monitors
            if left < m.x + m.width_in_pixels
            and left + width > m.x
            and top < m.y + m.height_in_pixels
            and top + height > m.y
        }
        if len(monitors) != 1:
            raise RuntimeError(
                "Move the game window fully onto one display before scanning."
            )
        monitor = monitors.pop()
        work_area = monitor
        desktop = root.get_full_property(
            connection.intern_atom("_NET_CURRENT_DESKTOP"), Xatom.CARDINAL
        )
        areas = root.get_full_property(
            connection.intern_atom("_NET_WORKAREA"), Xatom.CARDINAL
        )
        if desktop is not None and len(desktop.value) and areas is not None:
            index = 4 * int(desktop.value[0])
            area = areas.value[index : index + 4]
            if len(area) == 4:
                x, y, w, h = area
                clipped = (
                    max(monitor[0], x),
                    max(monitor[1], y),
                    min(monitor[2], x + w),
                    min(monitor[3], y + h),
                )
                if clipped[0] < clipped[2] and clipped[1] < clipped[3]:
                    work_area = clipped
        return (left, top, width, height), monitor, work_area


class _ScanWindow:
    def __init__(self, connection, window, bounds, surface):
        self.root = connection.screen().root
        self.active_atom = connection.get_atom("_NET_ACTIVE_WINDOW")
        self.window = window
        self.bounds = bounds
        self.surface = surface

    def check(self) -> None:
        if _active_id(self.root, self.active_atom) != self.window.id:
            raise RuntimeError("The game lost focus. Refocus it and restart the scan.")
        if _bounds(self.root, self.window) != self.bounds:
            raise RuntimeError(
                "The game window moved or changed size. Restart the scan."
            )

    def capture(self, region: tuple[int, int, int, int]) -> np.ndarray:
        self.check()
        left, top, width, height = region
        origin_x, origin_y, win_width, win_height = self.bounds
        x, y = left - origin_x, top - origin_y
        if x < 0 or y < 0 or x + width > win_width or y + height > win_height:
            raise ValueError(
                f"Capture region {region} extends outside the game window."
            )
        # The game draws to this surface outside Cairo between captures.
        self.surface.flush()
        self.surface.mark_dirty()
        image = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
        ctx = cairo.Context(image)
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_surface(self.surface, -x, -y)
        ctx.paint()
        image.flush()
        # Cairo RGB24 stores each pixel as the native integer 0x00RRGGBB.
        pixels = np.frombuffer(image.get_data(), dtype=np.uint32).astype(
            "<u4", copy=False
        )
        return pixels.view(np.uint8).reshape(height, width, 4)[:, :, :3].copy()


_current: ContextVar[_ScanWindow | None] = ContextVar(
    "xwayland_scan_window", default=None
)


@contextmanager
def scan_window(xid, bounds):
    with closing(display.Display()) as connection, ExitStack() as resources:
        window = connection.create_resource_object("window", xid)
        xcb = xcffib.connect()
        resources.callback(xcb.disconnect)
        screen = xcb.get_setup().roots[xcb.pref_screen]
        visual_id = window.get_attributes().visual
        visual = next(
            v
            for d in screen.allowed_depths
            for v in d.visuals
            if v.visual_id == visual_id
        )
        surface = cairo.XCBSurface(xcb, xid, visual, *bounds[2:])
        # Cairo caches its XCB device until it is finished, including across scans.
        device = cairo.cairo.cairo_surface_get_device(surface._pointer)
        resources.callback(cairo.cairo.cairo_device_finish, device)
        resources.callback(surface.finish)
        target = _ScanWindow(connection, window, bounds, surface)
        target.check()
        with _current.set(target):
            yield target


def check_input() -> None:
    target = _current.get()
    if target is not None:
        target.check()


def check_click(mouse, point: tuple[int, int]) -> None:
    target = _current.get()
    if target is None:
        return
    target.check()
    left, top, width, height = target.bounds
    x, y = point
    if not (left <= x < left + width and top <= y < top + height):
        raise RuntimeError("The click position is outside the game window.")
    deadline = time.monotonic() + 0.25
    while not pointer_at(mouse.position, point):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "The pointer did not reach the game position. Allow mouse control and restart the scan."
            )
        time.sleep(0.01)
        target.check()


def pointer_at(position, point) -> bool:
    # Fractional display scaling can round the requested position by one pixel.
    return abs(position[0] - point[0]) <= 1 and abs(position[1] - point[1]) <= 1


def capture_region(region: tuple[int, int, int, int]) -> np.ndarray:
    target = _current.get()
    if target is None:
        raise RuntimeError("XWayland capture requires an active scan window.")
    return target.capture(region)
