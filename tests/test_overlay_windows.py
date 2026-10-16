import sys
import time
import unittest


@unittest.skipUnless(sys.platform == "win32", "Windows overlay integration")
class WindowsOverlayTests(unittest.TestCase):
    def test_focus_first_click_and_capture_exclusion(self) -> None:
        import ctypes
        from ctypes import wintypes

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QWidget

        from autoscrapper.interaction.input_driver import leftClick
        from autoscrapper.interaction.ui_windows import capture_region
        from autoscrapper.overlay_window import OverlayWindow, _WindowsOverlay

        class TargetWindow(QWidget):
            clicks = 0

            def mousePressEvent(self, event) -> None:
                self.clicks += 1

        app = QApplication.instance() or QApplication([])
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        target = TargetWindow()
        target.setWindowFlags(Qt.FramelessWindowHint)
        target.setStyleSheet("background: #185fa3;")
        overlay = None

        def wait_for(condition) -> None:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                app.processEvents()
                if condition():
                    return
                time.sleep(0.01)
            self.assertTrue(condition())

        try:
            target.show()
            hwnd = wintypes.HWND(int(target.winId()))
            self.assertTrue(user32.SetWindowPos(hwnd, None, 40, 40, 900, 600, 0))
            user32.SetForegroundWindow(hwnd)
            wait_for(lambda: user32.GetForegroundWindow() == hwnd.value)
            sample = (670, 70, 40, 40)
            expected_bgr = (163, 95, 24)
            wait_for(lambda: (capture_region(sample) == expected_bgr).all())

            overlay = OverlayWindow()
            native = _WindowsOverlay(overlay, hwnd.value, [40, 40, 900, 600])
            self.assertEqual(user32.GetForegroundWindow(), hwnd.value)
            wait_for(overlay.isVisible)
            overlay.repaint()
            ctypes.WinDLL("dwmapi").DwmFlush()
            self.assertEqual(user32.GetForegroundWindow(), hwnd.value)
            self.assertTrue(
                user32.GetWindowLongW(wintypes.HWND(native.hwnd), -20) & 0x8
            )  # WS_EX_TOPMOST
            self.assertTrue((capture_region(sample) == expected_bgr).all())

            leftClick(720, 120)
            wait_for(lambda: target.clicks == 1)
            self.assertEqual(user32.GetForegroundWindow(), hwnd.value)

            target.hide()
            app.processEvents()
            native.refresh()
            self.assertFalse(overlay.isVisible())
            target.show()
            user32.SetForegroundWindow(hwnd)
            wait_for(lambda: user32.GetForegroundWindow() == hwnd.value)
            native.refresh()
            self.assertTrue(overlay.isVisible())
            self.assertEqual(user32.GetForegroundWindow(), hwnd.value)
        finally:
            if overlay is not None:
                overlay.close()
            target.close()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
