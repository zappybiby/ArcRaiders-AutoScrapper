"""Shared pytest fixtures and configuration for the test suite.

This conftest handles the cv2 import issue by providing a cv2 stub module
only when the real cv2 cannot be loaded (e.g., no libGL in CI).
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

HEAVY_MODULES = {
    "cv2",
    "mss",
    "mss.base",
    "mss.screenshot",
    "pywinctl",
    "pymonctl",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",
}


def _make_cv2_stub() -> ModuleType:
    """Create a cv2 stub that returns valid-enough values for testing."""
    stub = ModuleType("cv2")

    def _threshold(img, thresh, maxval, typ):
        import numpy as np

        is_inv = bool(typ & 1)
        mask = (img <= thresh) if is_inv else (img > thresh)
        return (thresh, mask.astype(np.uint8) * maxval)

    def _cvtColor(img, code):
        import numpy as np

        if code == 6:
            return np.dot(img[..., :3], [0.114, 0.587, 0.299]).astype(np.uint8)
        return img

    def _resize(img, dsize, fx=None, fy=None, interpolation=None):
        import numpy as np

        if hasattr(img, "shape") and len(img.shape) >= 2:
            h, w = img.shape[:2]
        else:
            h, w = 20, 20
        if dsize is None and fx is not None and fy is not None:
            return np.zeros((int(h * fy), int(w * fx), 3), dtype=np.uint8)
        elif dsize is not None:
            return np.zeros((*dsize[::-1], 3) if len(img.shape) == 3 else dsize[::-1], dtype=np.uint8)
        return img

    def _imread(path: str, flags=None):
        try:
            from PIL import Image
            import numpy as np

            img = Image.open(path)
            img = img.convert("RGB")
            return np.array(img)
        except Exception:
            import numpy as np

            return np.zeros((100, 100, 3), dtype=np.uint8)

    stub.threshold = _threshold
    stub.cvtColor = _cvtColor
    stub.imread = _imread
    stub.findContours = MagicMock(return_value=([], []))
    stub.contourArea = MagicMock(return_value=1000)
    stub.boundingRect = MagicMock(return_value=(0, 0, 100, 100))
    stub.minAreaRect = MagicMock(return_value=((50, 50), (100, 100), 0))
    stub.boxPoints = MagicMock(return_value=[[0, 0], [100, 0], [100, 100], [0, 100]])
    stub.drawContours = MagicMock()
    stub.resize = _resize
    stub.GaussianBlur = MagicMock()
    stub.Canny = MagicMock()
    stub.contours = MagicMock()
    stub.adaptiveThreshold = MagicMock()
    stub.bitwise_and = MagicMock()
    stub.bitwise_or = MagicMock()
    stub.bitwise_not = MagicMock()
    stub.morphologyEx = MagicMock()
    stub.erode = MagicMock()
    stub.dilate = MagicMock()
    stub.inRange = MagicMock()
    stub.putText = MagicMock()
    stub.rectangle = MagicMock()
    stub.circle = MagicMock()
    stub.line = MagicMock()
    stub.getTextSize = MagicMock(return_value=(10, 10, 0))
    stub.FONT_HERSHEY_SIMPLEX = 0
    stub.THRESH_BINARY = 0
    stub.THRESH_BINARY_INV = 1
    stub.THRESH_OTSU = 16
    stub.RETR_EXTERNAL = 0
    stub.RETR_LIST = 1
    stub.CHAIN_APPROX_SIMPLE = 2
    stub.COLOR_BGR2GRAY = 6
    stub.COLOR_BGR2RGB = 4
    stub.IMREAD_COLOR = 1
    stub.INTER_CUBIC = 2
    stub.INTER_LINEAR = 1
    stub.INTER_NEAREST = 0
    stub.INTER_LANCZOS4 = 4

    for attr, val in {
        "imwrite": MagicMock(),
        "imshow": MagicMock(),
        "waitKey": MagicMock(),
        "destroyAllWindows": MagicMock(),
        "VideoCapture": MagicMock(),
        "matchTemplate": MagicMock(),
        "minMaxLoc": MagicMock(),
        "normalize": MagicMock(),
        "kmeans": MagicMock(),
        "calcHist": MagicMock(),
        "createCLAHE": MagicMock(return_value=MagicMock()),
        "connectedComponentsWithStats": MagicMock(return_value=(1, None, [[0, 0, 100, 100, 10000]], None)),
        "CHAIN_APPROX_NONE": 1,
        "RETR_CCOMP": 2,
        "THRESH_TOZERO": 3,
        "LINE_AA": 8,
        "FILLED": -1,
    }.items():
        setattr(stub, attr, val)

    return stub


def _try_import_cv2() -> bool:
    """Try to import cv2, return True if successful."""
    try:
        import cv2  # noqa: F401

        return True
    except (ImportError, OSError):
        return False


_has_cv2 = _try_import_cv2()

for _mod_name in HEAVY_MODULES - {"cv2"}:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

if not _has_cv2:
    sys.modules["cv2"] = _make_cv2_stub()


@pytest.fixture(autouse=True)
def _reset_cv2_stub_per_test() -> None:
    """Reset cv2 stub state between tests to prevent cross-test contamination."""
    yield
    if "cv2" in sys.modules:
        stub = sys.modules["cv2"]
        for attr in dir(stub):
            val = getattr(stub, attr, None)
            if isinstance(val, MagicMock):
                val.reset_mock()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_cv2: mark test as requiring cv2/OpenCV to be fully functional (needs libGL)",
    )
