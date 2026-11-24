"""Window lookup and capture for games running through XWayland."""

from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
import time

import numpy as np
from Xlib import X, Xatom, display, error


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
    def __init__(self, connection, xid: int, bounds: tuple[int, int, int, int]):
        self.root = connection.screen().root
        self.active_atom = connection.intern_atom("_NET_ACTIVE_WINDOW")
        self.window = connection.create_resource_object("window", xid)
        self.bounds = bounds

        visual_id = self.window.get_attributes().visual
        screen = connection.screen()
        depth, visual = next(
            (depth.depth, visual)
            for depth in screen.allowed_depths
            for visual in depth.visuals
            if visual.visual_id == visual_id
        )
        info = connection.display.info
        fmt = next(f for f in info.pixmap_formats if f.depth == depth)
        if visual.visual_class != X.TrueColor or fmt.bits_per_pixel not in (16, 32):
            raise RuntimeError(
                f"Unsupported XWayland window pixel format ({depth}-bit depth, {fmt.bits_per_pixel} bits per pixel)."
            )
        self.masks = (visual.blue_mask, visual.green_mask, visual.red_mask)
        byte_order = "<" if info.image_byte_order == X.LSBFirst else ">"
        self.dtype = np.dtype(f"{byte_order}u{fmt.bits_per_pixel // 8}")
        self.scanline_pad = fmt.scanline_pad
        self.bgrx = (
            byte_order == "<"
            and self.dtype.itemsize == 4
            and self.masks == (0xFF, 0xFF00, 0xFF0000)
        )

    def focused(self) -> bool:
        return _active_id(self.root, self.active_atom) == self.window.id

    def check(self) -> None:
        if not self.focused():
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
        image = self.window.get_image(x, y, width, height, X.ZPixmap, 0xFFFFFFFF)
        if self.bgrx:
            return (
                np.frombuffer(image.data, np.uint8)
                .reshape(height, width, 4)[:, :, :3]
                .copy()
            )

        pad_bytes = self.scanline_pad // 8
        stride = (width * self.dtype.itemsize + pad_bytes - 1) // pad_bytes * pad_bytes
        pixels = np.ndarray(
            (height, width),
            self.dtype,
            image.data,
            strides=(stride, self.dtype.itemsize),
        ).astype(np.uint32)
        result = np.empty((height, width, 3), dtype=np.uint8)
        for i, mask in enumerate(self.masks):
            shift = (mask & -mask).bit_length() - 1
            maximum = mask >> shift
            result[:, :, i] = (
                ((pixels & mask) >> shift) * 255 + maximum // 2
            ) // maximum
        return result


_current: ContextVar[_ScanWindow | None] = ContextVar(
    "xwayland_scan_window", default=None
)


@contextmanager
def scan_window(xid, bounds):
    with closing(display.Display()) as connection:
        target = _ScanWindow(connection, xid, bounds)
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
                "The pointer did not reach the selected position in the game."
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
