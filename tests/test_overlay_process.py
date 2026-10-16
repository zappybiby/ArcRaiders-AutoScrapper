import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from autoscrapper.overlay import ScanOverlay


class OverlayProcessTests(unittest.TestCase):
    def test_exited_child_can_be_closed_after_broken_pipe(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        child.wait()
        with (
            patch("autoscrapper.overlay.subprocess.Popen", return_value=child),
            patch("autoscrapper.overlay.subprocess.CREATE_NO_WINDOW", 0, create=True),
        ):
            overlay = ScanOverlay(1, (0, 0, 1920, 1080))
        try:
            deadline = time.monotonic() + 2
            while not overlay.error and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(overlay.error)
            self.assertFalse(overlay.ready)
        finally:
            overlay.close()
        self.assertTrue(child.stdin.closed)
        self.assertTrue(child.stdout.closed)
