"""Qt scan display, run in its own process by the overlay controller."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import queue
import sys
import threading

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QApplication, QWidget

COLORS = {
    "KEEP": "#86efac",
    "RECYCLE": "#93c5fd",
    "SELL": "#fde047",
    "SKIP": "#fdba74",
    "UNREADABLE": "#fdba74",
    "RETRYING": "#c4b5fd",
}
ACTIONS = {
    "KEEP": "KEPT",
    "RECYCLE": "RECYCLED",
    "SELL": "SOLD",
    "SKIP": "SKIPPED",
    "UNREADABLE": "UNREADABLE",
}
FOREGROUND = "#e5e7eb"
SECONDARY = "#a9b7ca"


def _font(size: int, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(["DejaVu Sans Mono", "Consolas", "monospace"])
    font.setPixelSize(size)
    font.setBold(bold)
    return font


class OverlayWindow(QWidget):
    """The view is independent of the Windows window-management code."""

    def __init__(self) -> None:
        super().__init__()
        self.state: dict = {}
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(640, 360)

    def update_state(self, state: dict) -> None:
        self.state = state
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b1220"))
        scale = min(self.width() / 640, self.height() / 360)
        painter.translate((self.width() - 640 * scale) / 2, 0)
        painter.scale(scale, scale)
        painter.setRenderHint(QPainter.TextAntialiasing)

        def text(
            value,
            x,
            y,
            width,
            height,
            size,
            *,
            bold=False,
            color=FOREGROUND,
            right=False,
        ):
            font = _font(size, bold)
            painter.setFont(font)
            painter.setPen(QColor(color))
            value = QFontMetricsF(font).elidedText(str(value), Qt.ElideRight, width)
            alignment = Qt.AlignVCenter | (Qt.AlignRight if right else Qt.AlignLeft)
            painter.drawText(QRectF(x, y, width, height), alignment, value)

        state = self.state
        phase = state.get("phase") or "Scanning…"
        page = state.get("page", 1)
        suffix = f"· Page {page}"
        if state.get("dry_run"):
            suffix = f"· Dry run {suffix}"
        suffix_width = QFontMetricsF(_font(24)).horizontalAdvance(suffix)
        phase_width = min(
            QFontMetricsF(_font(28, True)).horizontalAdvance(phase), 580 - suffix_width
        )
        text(phase, 20, 24, phase_width + 1, 42, 28, bold=True, color="#7dd3fc")
        text(suffix, 40 + phase_width, 24, suffix_width + 1, 42, 24, color=SECONDARY)

        completed = int(state.get("completed", 0))
        count_width = QFontMetricsF(_font(48, True)).horizontalAdvance(str(completed))
        text(completed, 20, 90, count_width + 1, 66, 48, bold=True)
        text(
            "items processed",
            40 + count_width,
            90,
            580 - count_width,
            66,
            32,
            bold=True,
        )
        painter.setPen(QColor("#334155"))
        painter.drawLine(20, 164, 620, 164)

        retrying = state.get("retrying", False)
        text(
            "Current item" if retrying else "Last item",
            20,
            175,
            600,
            30,
            22,
            color=SECONDARY,
        )
        outcome = "RETRYING" if retrying else state.get("outcome", "")
        action = (
            outcome
            if state.get("dry_run") and outcome in {"KEEP", "RECYCLE", "SELL"}
            else ACTIONS.get(outcome, outcome)
        )
        action_width = QFontMetricsF(_font(48, True)).horizontalAdvance(action)
        item_width = 580 - action_width if action else 600
        text(state.get("item") or "—", 20, 205, item_width, 56, 40, bold=True)
        text(
            action,
            620 - action_width,
            205,
            action_width + 1,
            56,
            48,
            bold=True,
            color=COLORS.get(outcome, FOREGROUND),
            right=True,
        )
        painter.setPen(QColor("#334155"))
        painter.drawLine(20, 269, 620, 269)

        counts = state.get("counts", {})
        entries = [
            (key, int(counts.get(key, 0)))
            for key in ACTIONS
            if key in {"KEEP", "RECYCLE", "SELL"} or counts.get(key, 0)
        ]
        size = 24
        while size > 12:
            metrics = QFontMetricsF(_font(size))
            bold_metrics = QFontMetricsF(_font(size, True))
            widths = [
                (
                    metrics.horizontalAdvance(f"{key} ")
                    + bold_metrics.horizontalAdvance(str(count))
                )
                for key, count in entries
            ]
            if sum(widths) + 20 * (len(entries) - 1) <= 600:
                break
            size -= 1
        x = 20
        for key, count in entries:
            label_width = QFontMetricsF(_font(size)).horizontalAdvance(f"{key} ")
            number_width = QFontMetricsF(_font(size, True)).horizontalAdvance(
                str(count)
            )
            text(f"{key} ", x, 278, label_width + 1, 32, size, color=COLORS[key])
            text(count, x + label_width, 278, number_width + 1, 32, size, bold=True)
            x += label_width + number_width + 20

        elapsed = state.get("elapsed")
        seconds = max(0, int(elapsed or 0))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        duration = (
            f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            if hours
            else f"{minutes:02d}:{seconds:02d}"
        )
        speed = completed / elapsed if elapsed and elapsed > 0 else 0
        text(
            f"{duration} elapsed · {speed:.2f} items/s",
            20,
            313,
            600,
            34,
            26,
            color=SECONDARY,
        )


class _WindowsOverlay:
    def __init__(self, window: OverlayWindow, target: int, rect: list[int]) -> None:
        self.window = window
        self.target = target
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        for name, args, result in (
            ("IsWindow", [wintypes.HWND], wintypes.BOOL),
            ("IsIconic", [wintypes.HWND], wintypes.BOOL),
            ("GetForegroundWindow", [], wintypes.HWND),
            (
                "GetWindowRect",
                [wintypes.HWND, ctypes.POINTER(wintypes.RECT)],
                wintypes.BOOL,
            ),
            (
                "SetWindowDisplayAffinity",
                [wintypes.HWND, wintypes.DWORD],
                wintypes.BOOL,
            ),
            (
                "SetWindowPos",
                [
                    wintypes.HWND,
                    wintypes.HWND,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    wintypes.UINT,
                ],
                wintypes.BOOL,
            ),
        ):
            function = getattr(self.user32, name)
            function.argtypes = args
            function.restype = result
        if not self.user32.IsWindow(target):
            raise RuntimeError("Game window no longer exists")
        self.hwnd = int(window.winId())
        if not self.user32.SetWindowDisplayAffinity(self.hwnd, 0x11):
            raise ctypes.WinError(ctypes.get_last_error())
        self.rect: list[int] = []
        self.position(rect)
        self.refresh()

    def position(self, rect: list[int]) -> None:
        left, top, width, height = rect
        overlay_width, overlay_height = width // 3, height // 3
        if not self.user32.SetWindowPos(
            self.hwnd,
            wintypes.HWND(-1),
            left + width - overlay_width,
            top,
            overlay_width,
            overlay_height,
            0x0010,  # HWND_TOPMOST, SWP_NOACTIVATE
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.rect = rect

    def refresh(self) -> None:
        if not self.user32.IsWindow(self.target):
            self.window.close()
            QApplication.instance().quit()
            return
        active = (
            self.user32.GetForegroundWindow() == self.target
            and not self.user32.IsIconic(self.target)
        )
        bounds = wintypes.RECT()
        if not self.user32.IsIconic(self.target) and self.user32.GetWindowRect(
            self.target, ctypes.byref(bounds)
        ):
            rect = [
                bounds.left,
                bounds.top,
                bounds.right - bounds.left,
                bounds.bottom - bounds.top,
            ]
            if rect != self.rect:
                self.position(rect)
        if active and not self.window.isVisible():
            self.window.show()
            self.position(self.rect)
        elif not active and self.window.isVisible():
            self.window.hide()


def _reply(message: dict) -> None:
    print(json.dumps(message), flush=True)


def main() -> None:
    window = None
    try:
        if sys.platform != "win32":
            raise RuntimeError("The scan overlay requires Windows")
        initial = json.loads(sys.stdin.readline())
        app = QApplication([])
        window = OverlayWindow()
        native = _WindowsOverlay(window, initial["hwnd"], initial["rect"])
        app.processEvents()
        _reply({"ready": True})
    except Exception as error:
        if window is not None:
            window.hide()
        _reply({"error": str(error)})
        return

    messages: queue.SimpleQueue = queue.SimpleQueue()

    def read_updates() -> None:
        try:
            for line in sys.stdin:
                messages.put(json.loads(line))
        finally:
            messages.put(None)

    def refresh() -> None:
        try:
            while not messages.empty():
                state = messages.get_nowait()
                if state is None:
                    window.close()
                    app.quit()
                    return
                window.update_state(state)
            native.refresh()
        except Exception as error:
            window.hide()
            _reply({"error": str(error)})
            app.quit()

    threading.Thread(target=read_updates, daemon=True).start()
    timer = QTimer()
    timer.timeout.connect(refresh)
    timer.start(50)
    app.exec()


if __name__ == "__main__":
    main()
