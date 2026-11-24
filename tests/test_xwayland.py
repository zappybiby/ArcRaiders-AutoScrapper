import os
import shutil
import subprocess
import sys
import unittest
from contextlib import closing
from unittest.mock import patch


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("Xvfb"), "requires Xvfb"
)
class XWaylandWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server = subprocess.Popen(
            [
                "Xvfb",
                "-displayfd",
                "1",
                "-screen",
                "0",
                "320x240x24",
                "-screen",
                "1",
                "320x240x16",
                "-nolisten",
                "tcp",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        cls.addClassCleanup(server.stdout.close)
        cls.addClassCleanup(server.wait, 5)
        cls.addClassCleanup(server.terminate)
        cls.display = ":" + str(int(server.stdout.readline()))

    def test_capture_uses_window_coordinates_and_visual(self):
        from Xlib import X, Xatom, display
        from autoscrapper.interaction import xwayland

        for screen in (0, 1):
            with (
                self.subTest(screen=screen),
                patch.dict(os.environ, DISPLAY=f"{self.display}.{screen}"),
                closing(display.Display()) as d,
            ):
                root = d.screen().root
                w = root.create_window(
                    40,
                    25,
                    90,
                    65,
                    0,
                    X.CopyFromParent,
                    X.InputOutput,
                    X.CopyFromParent,
                    background_pixel=0,
                )
                w.set_wm_name("Game probe")
                w.map()
                red = d.screen().default_colormap.alloc_named_color("red").pixel
                w.fill_rectangle(w.create_gc(foreground=red), 7, 4, 5, 3)
                root.change_property(
                    d.intern_atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW, 32, [w.id]
                )
                d.sync()
                self.assertEqual(xwayland.active_target("GAME"), w.id)
                bounds, monitor, work_area = xwayland.window_geometry(w.id)
                self.assertEqual(monitor, work_area)
                self.assertEqual(bounds, (40, 25, 90, 65))
                with xwayland.scan_window(w.id, bounds):
                    frame = xwayland.capture_region((46, 29, 6, 3))
                    self.assertEqual(frame.shape, (3, 6, 3))
                    self.assertTrue((frame[:, 0] == 0).all())
                    self.assertTrue((frame[:, 1:] == (0, 0, 255)).all())
                    self.assertTrue(frame.flags.c_contiguous)
                with self.assertRaisesRegex(RuntimeError, "active scan"):
                    xwayland.capture_region((46, 29, 6, 3))

    def test_input_rechecks_original_window_and_bounds(self):
        from Xlib import X, Xatom, display
        from autoscrapper.interaction import xwayland

        with (
            patch.dict(os.environ, DISPLAY=self.display),
            closing(display.Display()) as d,
        ):
            root = d.screen().root
            active = d.intern_atom("_NET_ACTIVE_WINDOW")
            w = root.create_window(
                10, 20, 100, 80, 0, X.CopyFromParent, X.InputOutput, X.CopyFromParent
            )
            w.map()
            root.change_property(active, Xatom.WINDOW, 32, [w.id])
            d.sync()
            root.change_property(
                d.intern_atom("_NET_CURRENT_DESKTOP"), Xatom.CARDINAL, 32, [1]
            )
            root.change_property(
                d.intern_atom("_NET_WORKAREA"),
                Xatom.CARDINAL,
                32,
                [0, 0, 320, 240, 0, 10, 320, 230],
            )
            d.sync()
            bounds, monitor, work_area = xwayland.window_geometry(w.id)
            self.assertEqual(monitor, (0, 0, 320, 240))
            self.assertEqual(work_area, (0, 10, 320, 240))
            with xwayland.scan_window(w.id, bounds):
                w.configure(x=11)
                d.sync()
                with self.assertRaisesRegex(RuntimeError, "moved"):
                    xwayland.check_input()
                root.change_property(active, Xatom.WINDOW, 32, [root.id])
                d.sync()
                with self.assertRaisesRegex(RuntimeError, "lost focus"):
                    xwayland.check_input()
