"""
Contour-based grid detection for the 4x6 ARC Raiders inventory UI.

Slots are detected inside a normalized ROI so positions scale to any
resolution, and contours are used to allow partially visible cells
when the grid is vertically offset ("carousel" effect).
"""

from dataclasses import dataclass
from typing import Iterator, List, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GRID_COLS = 4  # 4 across
GRID_ROWS = 6  # 6 down

# Reference window size (the layout was captured at 1920x1080)
REF_WIDTH = 1920
REF_HEIGHT = 1080

# Inventory grid ROI normalized to the window (x, y, w, h)
GRID_ROI_NORM = (0.0745, 0.2444, 0.2208, 0.6380)

# Mouse-safe ROI outside the grid to avoid occluding cells during detection
SAFE_MOUSE_RECT_NORM = (0.1646, 0.1370, 0.0411, 0.0509)

# Approximate cell size (square) at reference resolution
REF_CELL_SIZE = 95

# Visibility requirement: at least 80% of cell height visible to count as valid
MIN_VISIBLE_RATIO = 0.8

# How much to shrink inside bounding boxes to avoid borders/bleed
SHRINK_RATIO_X = 0.1
SHRINK_RATIO_Y = 0.1

# Size tolerance when matching contours to expected cell size
CELL_SIZE_TOLERANCE = 0.3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """Represents a single grid cell."""

    index: int  # 0..(GRID_ROWS*GRID_COLS-1), row-major
    row: int  # 0..GRID_ROWS-1 (top to bottom)
    col: int  # 0..GRID_COLS-1 (left to right)
    x: int  # top-left x in pixels (window-relative)
    y: int  # top-left y in pixels (window-relative)
    width: int  # visible width
    height: int  # visible height
    safe_bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2) window-relative

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """(x, y, w, h) rectangle in pixels."""
        return self.x, self.y, self.width, self.height

    @property
    def safe_rect(self) -> Tuple[int, int, int, int]:
        """Shrunken rectangle inside the cell (x, y, w, h)."""
        x1, y1, x2, y2 = self.safe_bounds
        return x1, y1, x2 - x1, y2 - y1

    @property
    def center(self) -> Tuple[float, float]:
        """
        Center of the safe rectangle in pixels (cx, cy).
        Using the safe rectangle keeps the cursor away from borders.
        """
        x1, y1, x2, y2 = self.safe_bounds
        cx = x1 + (x2 - x1) / 2.0
        cy = y1 + (y2 - y1) / 2.0
        return cx, cy

    @property
    def safe_center(self) -> Tuple[float, float]:
        """Alias for center for readability."""
        return self.center


# ---------------------------------------------------------------------------
# Grid helper
# ---------------------------------------------------------------------------


class Grid:
    COLS = GRID_COLS
    ROWS = GRID_ROWS

    def __init__(
        self,
        cells: List[Cell],
        roi_rect: Tuple[int, int, int, int],
        window_width: int,
        window_height: int,
    ):
        self._cells = cells
        self.roi_rect = roi_rect
        self.window_width = window_width
        self.window_height = window_height

    @classmethod
    def detect(
        cls,
        inv_bgr: np.ndarray,
        roi_rect: Tuple[int, int, int, int],
        window_width: int,
        window_height: int,
    ) -> "Grid":
        """
        Build a grid by detecting cell contours inside the provided ROI image.
        inv_bgr: BGR image cropped to the inventory ROI (window-relative).
        roi_rect: (x, y, w, h) of the ROI in window-relative pixels.
        """
        expected_size = _scaled_cell_size(window_width, window_height)
        detections = _detect_cells_by_contours(inv_bgr, expected_size)

        cells: List[Cell] = []
        roi_x, roi_y, _, _ = roi_rect

        for idx, det in enumerate(detections):
            dx, dy, dw, dh = det["x"], det["y"], det["w"], det["h"]
            sx1, sy1, sx2, sy2 = det["safe_bounds"]
            abs_safe = (roi_x + sx1, roi_y + sy1, roi_x + sx2, roi_y + sy2)
            cells.append(
                Cell(
                    index=idx,
                    row=idx // cls.COLS,
                    col=idx % cls.COLS,
                    x=roi_x + dx,
                    y=roi_y + dy,
                    width=dw,
                    height=dh,
                    safe_bounds=abs_safe,
                )
            )

        return cls(cells, roi_rect, window_width, window_height)

    # ---- Accessors --------------------------------------------------------

    def __len__(self) -> int:
        """Total number of cells."""
        return len(self._cells)

    def __iter__(self) -> Iterator[Cell]:
        """Iterate cells row-by-row, left-to-right, top-to-bottom."""
        return iter(self._cells)

    def cell_by_index(self, index: int) -> Cell:
        """
        Get cell by linear index (row-major).
        index: 0..len(grid)-1
        """
        return self._cells[index]

    def cell(self, row: int, col: int) -> Cell:
        """
        Get cell by (row, col).
        row: 0..ROWS-1
        col: 0..COLS-1
        """
        idx = row * self.COLS + col
        return self._cells[idx]

    def center_by_index(self, index: int) -> Tuple[float, float]:
        """Center (cx, cy) of cell with given row-major index."""
        return self.cell_by_index(index).center

    def center(self, row: int, col: int) -> Tuple[float, float]:
        """Center (cx, cy) of cell at (row, col)."""
        return self.cell(row, col).center


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def normalized_rect_to_window(
    norm_rect: Tuple[float, float, float, float],
    window_width: int,
    window_height: int,
) -> Tuple[int, int, int, int]:
    """
    Scale a normalized rectangle (x, y, w, h in [0,1]) to window-relative pixels.
    """
    nx, ny, nw, nh = norm_rect
    x = int(round(nx * window_width))
    y = int(round(ny * window_height))
    w = max(1, int(round(nw * window_width)))
    h = max(1, int(round(nh * window_height)))
    return x, y, w, h


def inventory_roi_rect(
    window_width: int, window_height: int
) -> Tuple[int, int, int, int]:
    """
    Window-relative rectangle for the inventory grid ROI.
    """
    return normalized_rect_to_window(GRID_ROI_NORM, window_width, window_height)


def safe_mouse_point(window_width: int, window_height: int) -> Tuple[int, int]:
    """
    Window-relative point to park the mouse while detecting cells.
    """
    sx, sy, sw, sh = normalized_rect_to_window(
        SAFE_MOUSE_RECT_NORM, window_width, window_height
    )
    return sx + sw // 2, sy + sh // 2


def grid_center_point(window_width: int, window_height: int) -> Tuple[int, int]:
    """
    Window-relative center point of the grid ROI (useful for scrolling).
    """
    gx, gy, gw, gh = inventory_roi_rect(window_width, window_height)
    return gx + gw // 2, gy + gh // 2


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _scaled_cell_size(window_width: int, window_height: int) -> int:
    """
    Scale the reference cell size to the current window.
    """
    scale_x = window_width / REF_WIDTH
    scale_y = window_height / REF_HEIGHT
    scale = (scale_x + scale_y) / 2.0
    return max(1, int(round(REF_CELL_SIZE * scale)))


def _detect_cells_by_contours(inv_bgr: np.ndarray, cell_size: int) -> List[dict]:
    """
    Detect cell bounding boxes within the inventory ROI using contours.
    Returns a list of dictionaries:
      {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "safe_bounds": (ix1, iy1, ix2, iy2),
      }
    """
    if inv_bgr.size == 0:
        return []

    h, w = inv_bgr.shape[:2]

    gray = cv2.cvtColor(inv_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cells: List[dict] = []
    min_w = cell_size * (1.0 - CELL_SIZE_TOLERANCE)
    max_w = cell_size * (1.0 + CELL_SIZE_TOLERANCE)
    min_h = cell_size * MIN_VISIBLE_RATIO
    max_h = cell_size * (1.0 + CELL_SIZE_TOLERANCE)

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)

        if bw < min_w or bw > max_w:
            continue
        if bh < min_h or bh > max_h:
            continue

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + bw)
        y2 = min(h, y + bh)

        vis_w = x2 - x1
        vis_h = y2 - y1
        if vis_w <= 0 or vis_h <= 0:
            continue

        pad_x = int(vis_w * SHRINK_RATIO_X)
        pad_y = int(vis_h * SHRINK_RATIO_Y)

        ix1 = x1 + pad_x
        iy1 = y1 + pad_y
        ix2 = x2 - pad_x
        iy2 = y2 - pad_y

        if ix2 <= ix1 or iy2 <= iy1:
            continue

        cells.append(
            {
                "x": x1,
                "y": y1,
                "w": vis_w,
                "h": vis_h,
                "safe_bounds": (ix1, iy1, ix2, iy2),
            }
        )

    cells.sort(key=lambda c: (c["y"], c["x"]))
    return cells
