from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import cv2
import numpy as np
from rapidfuzz import fuzz, process

from ..core.item_actions import clean_ocr_text
from ..items import rules_store
from .tesseract import image_to_data, image_to_string

# Infobox visual characteristics
INFOBOX_COLOR_BGR = np.array([236, 246, 253], dtype=np.uint8)  # #fdf6ec in BGR
INFOBOX_TOLERANCE_MIN = 5
INFOBOX_TOLERANCE_MAX = 30
INFOBOX_TOLERANCE_MAX_WIDE = 50
INFOBOX_TOLERANCE_PADDING = 2.0
INFOBOX_CLOSE_KERNEL_MIN = 7
INFOBOX_CLOSE_KERNEL_MAX = 15
INFOBOX_CLOSE_DIVISOR = 150.0
INFOBOX_EDGE_FRACTION = 0.55
INFOBOX_MIN_AREA = 1000

# Item title placement inside the infobox (relative to infobox size).
# OCR only needs the top band; 22% matches the title area selected by the
# existing top-of-infobox line filter in _extract_title_from_data.
TITLE_HEIGHT_REL = 0.22

# Confirmation buttons (window-normalized rectangles)
SELL_CONFIRM_RECT_NORM = (0.5047, 0.6941, 0.1791, 0.0531)
RECYCLE_CONFIRM_RECT_NORM = (0.5058, 0.6274, 0.1777, 0.0544)

# Inventory count ROI (window-normalized rectangle)
# Matches the always-visible "items in stash" label near the top-left.
INVENTORY_COUNT_RECT_NORM = (0.0734, 0.1583, 0.0760, 0.0231)

_OCR_DEBUG_DIR: Optional[Path] = None
_last_roi_hash: Optional[bytes] = None
_last_ocr_result: Optional[Tuple[str, str]] = None
DEFAULT_ITEM_NAME_MATCH_THRESHOLD = 75
# Guarded fallback only uses these broad stat labels; extend this list if new
# infobox stat headings start outranking item titles in OCR output.
_STAT_LINE_KEYWORDS = (
    "accuracy",
    "ammo type",
    "arc armor",
    "armor penetration",
    "damage",
    "durability",
    "fire rate",
    "firing mode",
    "magazine size",
    "range",
    "rarity",
    "reload",
    "stack size",
    "value",
    "weight",
)
_STAT_LINE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(keyword) for keyword in _STAT_LINE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def reset_ocr_caches() -> None:
    """Reset module-level OCR caches. Call at the start of each scan session.

    Resets memoization caches (_last_roi_hash, _last_ocr_result, and rules_store._ITEM_NAMES).
    Does NOT reset _OCR_DEBUG_DIR — that is session-scoped configuration set by
    enable_ocr_debug(), not a cache, and must persist across scans within a
    process lifetime so debug output is not silently dropped mid-session.
    """
    global _last_roi_hash, _last_ocr_result
    _last_roi_hash = None
    _last_ocr_result = None
    rules_store.reset_item_names_cache()


@dataclass
class InfoboxOcrResult:
    item_name: str
    raw_item_text: str
    processed: np.ndarray
    preprocess_time: float
    ocr_time: float
    source: Literal["infobox", "context_menu"] = "infobox"
    ocr_failed: bool = False


@dataclass(frozen=True)
class ItemNameMatchResult:
    """
    Match metadata for OCR item-name resolution.

    `cleaned_text` is the OCR output after normalization. `chosen_name` is the
    caller-facing value (configured match or cleaned OCR fallback), while
    `matched_name` is only set when a configured item-name match cleared the
    fuzzy threshold.
    """

    cleaned_text: str
    chosen_name: str
    matched_name: str | None
    threshold: int


@dataclass
class InfoboxDetectionResult:
    rect: Optional[Tuple[int, int, int, int]]
    tolerance: int
    min_dist: float
    close_kernel: int
    contour_count: int
    candidate_count: int
    selected_area: Optional[int]
    selected_score: Optional[float]
    bbox_method: Optional[Literal["dominant_edge", "percentile_fallback"]]
    failure_reason: Optional[str]


def is_empty_cell(bright_fraction: float, gray_var: float, edge_fraction: float) -> bool:
    """
    Decide if a slot is empty based on precomputed metrics.

    Empirically tuned heuristic: mostly dark with low texture and few edges.
    """
    # Primary test: looks dark with few bright pixels
    if bright_fraction >= 0.03:
        return False

    # Fallback
    if gray_var > 700:
        return False
    if edge_fraction > 0.09:
        return False

    return True


def slot_metrics(
    slot_bgr: np.ndarray,
    v_thresh: int = 120,
    canny1: int = 50,
    canny2: int = 150,
) -> Tuple[float, float, float]:
    """
    Compute simple statistics for an inventory slot.

    Returns:
        (bright_fraction, gray_var, edge_fraction)
    """
    if slot_bgr.size == 0:
        raise ValueError("slot_bgr is empty (ROI outside image bounds?)")

    # Brightness stats from HSV V channel
    hsv = cv2.cvtColor(slot_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    bright_fraction = float(np.mean(v > v_thresh))

    # Grayscale variance = how textured / high-contrast the cell is
    gray = cv2.cvtColor(slot_bgr, cv2.COLOR_BGR2GRAY)
    gray_var = float(gray.var())

    # Edge density via Canny
    edges = cv2.Canny(gray, canny1, canny2)
    edge_fraction = float(np.count_nonzero(edges)) / edges.size

    return bright_fraction, gray_var, edge_fraction


def is_slot_empty(
    slot_bgr: np.ndarray,
    v_thresh: int = 120,
    canny1: int = 50,
    canny2: int = 150,
) -> bool:
    """
    Decide if an inventory slot is visually empty using slot metrics.
    """
    bright_fraction, gray_var, edge_fraction = slot_metrics(slot_bgr, v_thresh, canny1, canny2)
    return is_empty_cell(bright_fraction, gray_var, edge_fraction)


def _odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def _compute_auto_tolerance(
    bgr_image: np.ndarray,
    target_bgr: np.ndarray,
    tolerance_max: int = INFOBOX_TOLERANCE_MAX,
) -> Tuple[int, float]:
    image_f = bgr_image.astype(np.float32)
    target_f = target_bgr.astype(np.float32)
    dist = np.linalg.norm(image_f - target_f, axis=2)
    min_dist = float(dist.min()) if dist.size else float("inf")
    tol = int(np.ceil(min_dist + INFOBOX_TOLERANCE_PADDING))
    tol = int(np.clip(tol, INFOBOX_TOLERANCE_MIN, tolerance_max))
    return tol, min_dist


def _dominant_edge_bbox(
    contour: np.ndarray, image_width: int, image_height: int
) -> Optional[Tuple[int, int, int, int]]:
    points = contour.reshape(-1, 2)
    if points.size == 0:
        return None

    xs = points[:, 0]
    ys = points[:, 1]

    x_counts = np.bincount(xs, minlength=image_width)
    y_counts = np.bincount(ys, minlength=image_height)

    if x_counts.size == 0 or y_counts.size == 0:
        return None

    x_thr = float(x_counts.max()) * INFOBOX_EDGE_FRACTION
    y_thr = float(y_counts.max()) * INFOBOX_EDGE_FRACTION

    x_candidates = np.where(x_counts >= x_thr)[0]
    y_candidates = np.where(y_counts >= y_thr)[0]

    if len(x_candidates) < 2 or len(y_candidates) < 2:
        return None

    x0 = int(x_candidates.min())
    x1 = int(x_candidates.max())
    y0 = int(y_candidates.min())
    y1 = int(y_candidates.max())

    return x0, y0, max(1, x1 - x0 + 1), max(1, y1 - y0 + 1)


def _percentile_bbox_from_filled_contour(
    contour: np.ndarray, image_width: int, image_height: int
) -> Optional[Tuple[int, int, int, int]]:
    filled = np.zeros((image_height, image_width), dtype=np.uint8)
    cv2.drawContours(filled, [contour], contourIdx=-1, color=255, thickness=-1)
    ys, xs = np.where(filled > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None

    x0 = int(np.percentile(xs, 2))
    x1 = int(np.percentile(xs, 98))
    y0 = int(np.percentile(ys, 2))
    y1 = int(np.percentile(ys, 98))

    return x0, y0, max(1, x1 - x0 + 1), max(1, y1 - y0 + 1)


def _save_infobox_detection_debug_images(
    bgr_image: np.ndarray,
    mask: np.ndarray,
    mask_proc: np.ndarray,
    contour: Optional[np.ndarray],
    rect: Optional[Tuple[int, int, int, int]],
    tolerance: int,
    min_dist: float,
    bbox_method: Optional[str],
    failure_reason: Optional[str],
) -> None:
    if _OCR_DEBUG_DIR is None:
        return

    _save_debug_image("infobox_detect_raw", bgr_image)
    _save_debug_image("infobox_detect_mask", mask)
    _save_debug_image("infobox_detect_mask_proc", mask_proc)

    overlay = bgr_image.copy()
    if contour is not None:
        cv2.drawContours(overlay, [contour], -1, (0, 255, 255), 2)

    if rect is not None:
        x, y, w, h = rect
        color = (0, 255, 0) if bbox_method == "dominant_edge" else (0, 165, 255)
        cv2.rectangle(overlay, (x, y), (x + w - 1, y + h - 1), color, 2)

    line_1 = f"tol={tolerance} min_dist={min_dist:.2f}"
    method_text = bbox_method or "none"
    line_2 = f"method={method_text}"
    line_3 = f"reason={failure_reason}" if failure_reason else ""
    cv2.putText(
        overlay,
        line_1,
        (8, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        line_1,
        (8, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        line_2,
        (8, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        line_2,
        (8, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    if line_3:
        cv2.putText(
            overlay,
            line_3,
            (8, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            line_3,
            (8, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    _save_debug_image("infobox_detect_overlay", overlay)


def find_infobox_with_debug(
    bgr_image: np.ndarray,
    tolerance_max: int = INFOBOX_TOLERANCE_MAX,
) -> InfoboxDetectionResult:
    """
    Detect the infobox/context-menu panel using adaptive color tolerance and
    contour refinement. Returns the detected rect plus diagnostics.
    """
    if bgr_image.size == 0:
        return InfoboxDetectionResult(
            rect=None,
            tolerance=INFOBOX_TOLERANCE_MIN,
            min_dist=float("inf"),
            close_kernel=INFOBOX_CLOSE_KERNEL_MIN,
            contour_count=0,
            candidate_count=0,
            selected_area=None,
            selected_score=None,
            bbox_method=None,
            failure_reason="empty_image",
        )

    img_h, img_w = bgr_image.shape[:2]
    close_k = _odd(
        int(
            np.clip(
                round(min(img_w, img_h) / INFOBOX_CLOSE_DIVISOR),
                INFOBOX_CLOSE_KERNEL_MIN,
                INFOBOX_CLOSE_KERNEL_MAX,
            )
        )
    )

    tolerance, min_dist = _compute_auto_tolerance(bgr_image, INFOBOX_COLOR_BGR, tolerance_max)
    color = INFOBOX_COLOR_BGR.astype(np.int16)
    lower = np.clip(color - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(color + tolerance, 0, 255).astype(np.uint8)

    mask = cv2.inRange(bgr_image, lower, upper)
    close_kernel = np.ones((close_k, close_k), dtype=np.uint8)
    open_kernel = np.ones((3, 3), dtype=np.uint8)

    mask_proc = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    mask_proc = cv2.morphologyEx(mask_proc, cv2.MORPH_OPEN, open_kernel, iterations=1)

    contours, _ = cv2.findContours(mask_proc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour_count = len(contours)
    if not contours:
        _save_infobox_detection_debug_images(
            bgr_image,
            mask,
            mask_proc,
            contour=None,
            rect=None,
            tolerance=tolerance,
            min_dist=min_dist,
            bbox_method=None,
            failure_reason="no_contours",
        )
        return InfoboxDetectionResult(
            rect=None,
            tolerance=tolerance,
            min_dist=min_dist,
            close_kernel=close_k,
            contour_count=contour_count,
            candidate_count=0,
            selected_area=None,
            selected_score=None,
            bbox_method=None,
            failure_reason="no_contours",
        )

    candidates: List[Tuple[float, np.ndarray, int]] = []
    for contour in contours:
        _, _, bw, bh = cv2.boundingRect(contour)
        area = int(bw * bh)
        if area < INFOBOX_MIN_AREA:
            continue
        ar = float(bh) / float(max(bw, 1))
        score = float(area) * (1.0 + 0.3 * min(ar, 5.0))
        candidates.append((score, contour, area))

    if not candidates:
        _save_infobox_detection_debug_images(
            bgr_image,
            mask,
            mask_proc,
            contour=None,
            rect=None,
            tolerance=tolerance,
            min_dist=min_dist,
            bbox_method=None,
            failure_reason="no_scored_contours",
        )
        return InfoboxDetectionResult(
            rect=None,
            tolerance=tolerance,
            min_dist=min_dist,
            close_kernel=close_k,
            contour_count=contour_count,
            candidate_count=0,
            selected_area=None,
            selected_score=None,
            bbox_method=None,
            failure_reason="no_scored_contours",
        )

    selected_score, best_contour, selected_area = max(candidates, key=lambda item: item[0])

    dominant_bbox = _dominant_edge_bbox(best_contour, img_w, img_h)
    bbox_method: Optional[Literal["dominant_edge", "percentile_fallback"]]
    failure_reason: Optional[str]

    if dominant_bbox is not None:
        rect = dominant_bbox
        bbox_method = "dominant_edge"
        failure_reason = None
    else:
        percentile_bbox = _percentile_bbox_from_filled_contour(best_contour, img_w, img_h)
        if percentile_bbox is None:
            _save_infobox_detection_debug_images(
                bgr_image,
                mask,
                mask_proc,
                contour=best_contour,
                rect=None,
                tolerance=tolerance,
                min_dist=min_dist,
                bbox_method=None,
                failure_reason="percentile_fallback_failed",
            )
            return InfoboxDetectionResult(
                rect=None,
                tolerance=tolerance,
                min_dist=min_dist,
                close_kernel=close_k,
                contour_count=contour_count,
                candidate_count=len(candidates),
                selected_area=selected_area,
                selected_score=selected_score,
                bbox_method=None,
                failure_reason="percentile_fallback_failed",
            )
        rect = percentile_bbox
        bbox_method = "percentile_fallback"
        failure_reason = "dominant_edge_threshold_failed"

    _save_infobox_detection_debug_images(
        bgr_image,
        mask,
        mask_proc,
        contour=best_contour,
        rect=rect,
        tolerance=tolerance,
        min_dist=min_dist,
        bbox_method=bbox_method,
        failure_reason=failure_reason,
    )

    return InfoboxDetectionResult(
        rect=rect,
        tolerance=tolerance,
        min_dist=min_dist,
        close_kernel=close_k,
        contour_count=contour_count,
        candidate_count=len(candidates),
        selected_area=selected_area,
        selected_score=selected_score,
        bbox_method=bbox_method,
        failure_reason=failure_reason,
    )


def find_infobox(bgr_image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """
    Backward-compatible wrapper returning only the detected infobox rectangle.
    Returns (x, y, w, h) relative to the provided image, or None if not found.
    Retries once with a wider color tolerance to handle non-standard monitor
    gamma or HDR before returning None.
    """
    result = find_infobox_with_debug(bgr_image)
    if result.rect is not None:
        return result.rect
    wide_result = find_infobox_with_debug(bgr_image, tolerance_max=INFOBOX_TOLERANCE_MAX_WIDE)
    return wide_result.rect


# Positional fallback crop for the context-menu UI.
# The dark context menu opens to the LEFT of the right-clicked cell.  Its left
# edge sits approximately 43 px right of cell centre (measured from debug images:
# "Move to Backpack" loses ~37 px on the left when offset=80, so true edge ≈ 43).
# Using 35 gives an 8 px safety margin to the left of the menu edge.
# The item name header occupies the topmost row of the menu.  It sits roughly
# 10 px above cell centre (one ~40 px row above the first action button, which
# appears at crop-y≈10 when Y-offset=30).  Using -20 gives a 10 px safety
# margin above the item name row.
# Normalized context-menu crop offsets (calibrated at 1920x1080).
_CONTEXT_MENU_X_OFFSET_NORM = 35 / 1920
_CONTEXT_MENU_Y_OFFSET_NORM = -20 / 1080  # negative = crop starts above cell centre
_CONTEXT_MENU_WIDTH_NORM = 420 / 1920
_CONTEXT_MENU_HEIGHT_NORM = 450 / 1080


def find_context_menu_crop(
    bgr_image: np.ndarray,
    cell_center_x: int,
    cell_center_y: int,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Return a positional crop rect near the right-click context menu.

    Used as a fallback when color-based ``find_infobox`` fails because the
    game changed its item panel from a light-cream background to a dark
    context menu.  The caller must pass the window-relative cell center so
    the crop is anchored to the correct screen location.

    Returns ``None`` if the computed crop region does not contain the
    characteristic bright (cream/white) background of the context menu
    panel — for example when the context menu has not opened yet, has
    already closed, or the positional offset lands on a different UI
    element such as the dark LOADOUT equipment panel.
    """
    img_h, img_w = bgr_image.shape[:2]
    x_off = int(round(_CONTEXT_MENU_X_OFFSET_NORM * img_w))
    y_off = int(round(_CONTEXT_MENU_Y_OFFSET_NORM * img_h))
    crop_w = int(round(_CONTEXT_MENU_WIDTH_NORM * img_w))
    crop_h = int(round(_CONTEXT_MENU_HEIGHT_NORM * img_h))
    x = max(0, cell_center_x + x_off)
    y = max(0, cell_center_y + y_off)
    # Shift left/up if the crop would overflow the right or bottom edge so the full
    # width and height are preserved (sell/recycle labels are in the lower portion of
    # the context menu and would be silently truncated without the bottom guard).
    if x + crop_w > img_w:
        x = max(0, img_w - crop_w)
    if y + crop_h > img_h:
        y = max(0, img_h - crop_h)
    x2 = min(img_w, x + crop_w)
    y2 = min(img_h, y + crop_h)
    w, h = x2 - x, y2 - y
    min_dim = int(round(100 * min(img_w, img_h) / 1080))
    if w < min_dim or h < min_dim:
        return None
    # Brightness guard: verify the left half of the crop contains UI
    # content rather than empty stash background.  The context menu
    # (whether the old light-cream style or the current dark UI) has
    # text and panel elements that raise mean brightness above ~40,
    # while the empty stash/inventory background sits below ~30.
    # The previous threshold of 120 was calibrated for the old light
    # cream menu and incorrectly rejected the game's current dark
    # context menu (mean brightness ~60-100).
    crop_left_half = bgr_image[y : y2, x : x + max(1, w // 2)]
    if crop_left_half.size > 0:
        mean_brightness = float(np.mean(cv2.cvtColor(crop_left_half, cv2.COLOR_BGR2GRAY)))
        if mean_brightness < 40.0:
            return None
    return x, y, w, h


def title_roi(infobox_rect: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """
    Compute the ROI for the title text within the infobox.
    """
    x, y, w, h = infobox_rect
    title_h = int(TITLE_HEIGHT_REL * h)
    return x, y, w, max(1, title_h)


_TITLE_LEFT_PAD = 4  # px — keeps leftmost glyph column away from x=0 so
# Tesseract doesn't clip the leading character edge.


def _crop_title_strip(infobox_bgr: np.ndarray) -> np.ndarray:
    if infobox_bgr.size == 0:
        return infobox_bgr
    title_h = max(1, int(round(infobox_bgr.shape[0] * TITLE_HEIGHT_REL)))
    strip = infobox_bgr[:title_h, :]
    if strip.shape[1] > _TITLE_LEFT_PAD * 2:
        median_val = np.median(strip)
        pad = np.full(
            strip.shape[:1] + (int(_TITLE_LEFT_PAD),) + strip.shape[2:],
            median_val,
            dtype=strip.dtype,
        )
        strip = np.concatenate([pad, strip], axis=1)
    return strip


def match_item_name_result(raw: str, threshold: int | None = None) -> ItemNameMatchResult:
    cleaned = clean_ocr_text(raw)
    resolved_threshold = DEFAULT_ITEM_NAME_MATCH_THRESHOLD if threshold is None else threshold
    if not 0 <= resolved_threshold <= 100:
        raise ValueError("threshold must be between 0 and 100")
    if not cleaned:
        return ItemNameMatchResult(
            cleaned_text="",
            chosen_name="",
            matched_name=None,
            threshold=resolved_threshold,
        )

    match = process.extractOne(
        cleaned,
        rules_store.get_item_names(),
        scorer=fuzz.WRatio,
        score_cutoff=resolved_threshold,
    )
    if match is None:
        return ItemNameMatchResult(
            cleaned_text=cleaned,
            chosen_name=cleaned,
            matched_name=None,
            threshold=resolved_threshold,
        )

    matched_name = str(match[0])
    return ItemNameMatchResult(
        cleaned_text=cleaned,
        chosen_name=matched_name,
        matched_name=matched_name,
        threshold=resolved_threshold,
    )


def match_item_name(raw: str, threshold: int | None = None) -> str:
    return match_item_name_result(raw, threshold).chosen_name


def _hash_roi(image: np.ndarray) -> bytes:
    contiguous = np.ascontiguousarray(image)
    return hashlib.blake2b(contiguous.tobytes(), digest_size=16).digest()


def rect_center(rect: Tuple[int, int, int, int]) -> Tuple[int, int]:
    """
    Center (cx, cy) of a rectangle.
    """
    x, y, w, h = rect
    return x + w // 2, y + h // 2


def normalized_rect_to_window(
    norm_rect: Tuple[float, float, float, float],
    window_width: int,
    window_height: int,
) -> Tuple[int, int, int, int]:
    """
    Scale a normalized rectangle (x,y,w,h in [0,1]) to window-relative pixels.
    """
    nx, ny, nw, nh = norm_rect
    x = int(round(nx * window_width))
    y = int(round(ny * window_height))
    w = max(1, int(round(nw * window_width)))
    h = max(1, int(round(nh * window_height)))
    return x, y, w, h


def window_relative_to_screen(
    rect: Tuple[int, int, int, int],
    window_left: int,
    window_top: int,
) -> Tuple[int, int, int, int]:
    """
    Convert a window-relative rectangle to absolute screen coordinates.
    """
    x, y, w, h = rect
    return window_left + x, window_top + y, w, h


def inventory_count_rect(window_width: int, window_height: int) -> Tuple[int, int, int, int]:
    """
    Window-relative rectangle for the always-visible inventory count label.
    """
    return normalized_rect_to_window(INVENTORY_COUNT_RECT_NORM, window_width, window_height)


def sell_confirm_button_rect(
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> Tuple[int, int, int, int]:
    """
    Absolute screen rectangle for the Sell confirmation button.
    """
    rel_rect = normalized_rect_to_window(SELL_CONFIRM_RECT_NORM, window_width, window_height)
    return window_relative_to_screen(rel_rect, window_left, window_top)


def recycle_confirm_button_rect(
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> Tuple[int, int, int, int]:
    """
    Absolute screen rectangle for the Recycle confirmation button.
    """
    rel_rect = normalized_rect_to_window(RECYCLE_CONFIRM_RECT_NORM, window_width, window_height)
    return window_relative_to_screen(rel_rect, window_left, window_top)


def sell_confirm_button_center(
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> Tuple[int, int]:
    """
    Center of the Sell confirmation button (absolute screen coords).
    """
    return rect_center(sell_confirm_button_rect(window_left, window_top, window_width, window_height))


def recycle_confirm_button_center(
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> Tuple[int, int]:
    """
    Center of the Recycle confirmation button (absolute screen coords).
    """
    return rect_center(recycle_confirm_button_rect(window_left, window_top, window_width, window_height))


def preprocess_for_ocr(roi_bgr: np.ndarray, *, restrict_otsu_to_left: bool = False) -> np.ndarray:
    if roi_bgr.size == 0:
        raise ValueError(f"preprocess_for_ocr: empty input array (shape={roi_bgr.shape})")
    roi_bgr = cv2.resize(roi_bgr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    if restrict_otsu_to_left:
        # Compute the Otsu threshold from the left half only (context-menu panel
        # side) so that bright inventory-grid icons on the right do not bias the
        # global threshold used for the menu text.
        w_g = gray.shape[1]
        if w_g // 2 > 0:
            thresh, _ = cv2.threshold(gray[:, : w_g // 2], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, binary = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
    else:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Tesseract expects dark text on light background. If the background is dark
    # (e.g. the game's new dark context-menu UI), invert so text becomes dark.
    # Sample only the left half of the image for the inversion check. The
    # context-menu panel is always on the left side of the crop; the right side
    # contains the game's inventory grid which can be bright (light item icons)
    # and would flip the polarity decision if included in the sample.
    h, w = binary.shape[:2]
    centre = binary[h // 4 : 3 * h // 4, 0 : w // 2]
    if centre.size == 0:
        centre = binary[:, 0 : w // 2]
    if centre.size == 0:
        centre = binary
    if float(np.mean(centre)) < 128.0:
        binary = cv2.bitwise_not(binary)
    return binary


def enable_ocr_debug(debug_dir: Path) -> None:
    """
    Enable saving OCR debug images into the provided directory.
    """
    global _OCR_DEBUG_DIR
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        _OCR_DEBUG_DIR = debug_dir
        print(f"[vision_ocr] OCR debug output enabled at {_OCR_DEBUG_DIR}", flush=True)
    except Exception as exc:
        print(f"[vision_ocr] failed to enable OCR debug dir: {exc}", flush=True)
        _OCR_DEBUG_DIR = None


def _save_debug_image(name: str, image: np.ndarray) -> None:
    """
    Write a debug image if a debug directory has been configured.
    """
    if _OCR_DEBUG_DIR is None:
        return
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{time.time_ns() % 1_000_000_000:09d}_{name}.webp"
    path = _OCR_DEBUG_DIR / filename
    try:
        cv2.imwrite(str(path), image, [cv2.IMWRITE_WEBP_QUALITY, 80])
    except Exception as exc:  # pragma: no cover - filesystem dependent
        print(f"[vision_ocr] failed to save debug image {path}: {exc}", flush=True)


def _extract_title_from_data(
    ocr_data: Dict[str, List],
    image_height: int,
    top_fraction: float = 0.22,
) -> Tuple[str, str]:
    """
    Choose the best-confidence line near the top of the infobox as the title.
    """
    texts = ocr_data.get("text", [])
    if not texts:
        return "", ""

    cutoff = max(1.0, float(image_height) * top_fraction)
    groups: Dict[Tuple[int, int, int, int], List[int]] = defaultdict(list)
    n = len(texts)
    for i in range(n):
        raw_text = texts[i] or ""
        cleaned = clean_ocr_text(raw_text)
        if not cleaned:
            continue

        top = float(ocr_data["top"][i])
        height = float(ocr_data["height"][i])
        center_y = top + (height / 2.0)
        if center_y > cutoff:
            continue

        key = (
            int(ocr_data["page_num"][i]),
            int(ocr_data["block_num"][i]),
            int(ocr_data["par_num"][i]),
            int(ocr_data["line_num"][i]),
        )
        groups[key].append(i)

    if not groups:
        return "", ""

    def _group_score(indices: List[int]) -> float:
        confs = []
        for idx in indices:
            try:
                confs.append(float(ocr_data["conf"][idx]))
            except Exception:
                continue
        return sum(confs) / len(confs) if confs else -1.0

    scored = {k: _group_score(groups[k]) for k in groups}
    best_score = max(scored.values())
    if best_score < 0:
        return "", ""

    def _group_top(key: Tuple[int, int, int, int]) -> float:
        return min(float(ocr_data["top"][i]) for i in groups[key])

    def _group_text(
        key: Tuple[int, int, int, int],
    ) -> Tuple[str, str]:
        ordered_indices = sorted(groups[key])
        cleaned_parts = []
        raw_parts = []
        for i in ordered_indices:
            if not texts[i]:
                continue
            raw_text = (texts[i] or "").strip()
            raw_parts.append(raw_text)
            cleaned = clean_ocr_text(raw_text)
            if cleaned:
                cleaned_parts.append(cleaned)
        return (
            " ".join(p for p in cleaned_parts if p).strip(),
            " ".join(p for p in raw_parts if p).strip(),
        )

    def _looks_like_stat_line(cleaned_text: str) -> bool:
        lowered = cleaned_text.casefold()
        return bool(lowered) and _STAT_LINE_PATTERN.search(lowered) is not None

    ranked_keys = sorted(groups, key=lambda k: (-scored[k], _group_top(k)))
    if not ranked_keys:
        return "", ""
    primary_text, primary_raw = _group_text(ranked_keys[0])
    primary_result = match_item_name_result(primary_text)
    if primary_result.matched_name is not None or not _looks_like_stat_line(primary_text):
        return primary_result.chosen_name, primary_raw

    for candidate_key in ranked_keys[1:]:
        candidate_text, candidate_raw = _group_text(candidate_key)
        if not candidate_text or _looks_like_stat_line(candidate_text):
            continue
        candidate_result = match_item_name_result(candidate_text)
        if candidate_result.matched_name is not None:
            return candidate_result.chosen_name, candidate_raw

    return primary_result.chosen_name, primary_raw


def _extract_cropped_title_from_data(ocr_data: Dict[str, List], image_height: int) -> Tuple[str, str]:
    """
    Extract a title from OCR data that was already cropped to the title strip.
    """
    return _extract_title_from_data(ocr_data, image_height, top_fraction=1.0)


def _extract_action_line_bbox(
    ocr_data: Dict[str, List],
    target: Literal["sell", "recycle"],
) -> Optional[Tuple[int, int, int, int]]:
    """
    Given OCR data, return a bbox (left, top, w, h) for
    the line containing the target action (infobox-relative coords).
    """
    groups: defaultdict[Tuple[int, int, int, int], List[int]] = defaultdict(list)
    texts = ocr_data.get("text", [])
    n = len(texts)
    page_nums = [int(v) for v in ocr_data.get("page_num", [])]
    block_nums = [int(v) for v in ocr_data.get("block_num", [])]
    par_nums = [int(v) for v in ocr_data.get("par_num", [])]
    line_nums = [int(v) for v in ocr_data.get("line_num", [])]

    for i in range(n):
        raw_text = texts[i] or ""
        cleaned = re.sub(r"[^a-z]", "", raw_text.lower())
        if not cleaned or target not in cleaned:
            continue
        key = (
            page_nums[i],
            block_nums[i],
            par_nums[i],
            line_nums[i],
        )
        groups[key].append(i)

    if not groups:
        return None

    def _group_score(indices: List[int]) -> float:
        confs = []
        for idx in indices:
            conf_str = ocr_data["conf"][idx]
            try:
                confs.append(float(conf_str))
            except Exception:
                continue
        return sum(confs) / len(confs) if confs else -1.0

    best_key = max(groups.keys(), key=lambda k: _group_score(groups[k]))
    # Expand to all words on the winning line, not just the ones containing the
    # target token.  This ensures the price token "(+11,000)" next to "Sell" is
    # included in the bbox even though it doesn't contain the target string.
    widths = [int(v) for v in ocr_data.get("width", [0] * n)]
    bp, bb, bpa, bl = best_key
    indices = [
        i
        for i in range(n)
        if page_nums[i] == bp and block_nums[i] == bb and par_nums[i] == bpa and line_nums[i] == bl and widths[i] > 0
    ]
    # If every word on the line has width==0 (degenerate tesserocr output), fall
    # back to the original group indices so min/max never operate on empty lists.
    if not indices:
        indices = list(groups[best_key])
    lefts = [int(ocr_data["left"][i]) for i in indices]
    tops = [int(ocr_data["top"][i]) for i in indices]
    rights = [int(ocr_data["left"][i]) + int(ocr_data["width"][i]) for i in indices]
    bottoms = [int(ocr_data["top"][i]) + int(ocr_data["height"][i]) for i in indices]

    x1, y1 = min(lefts), min(tops)
    x2, y2 = max(rights), max(bottoms)
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def find_action_bbox_by_ocr(
    infobox_bgr: np.ndarray,
    target: Literal["sell", "recycle"],
) -> Tuple[Optional[Tuple[int, int, int, int]], np.ndarray]:
    """
    Run OCR over the full infobox to locate the line containing the target
    action. Returns (bbox, processed_image) where bbox is infobox-relative.
    """
    processed = preprocess_for_ocr(infobox_bgr, restrict_otsu_to_left=True)
    try:
        data = image_to_data(processed)
    except Exception as exc:  # pragma: no cover - OCR-backend dependent
        print(
            f"[vision_ocr] ocr_backend image_to_data failed for target={target}; falling back to no bbox. error={exc}",
            flush=True,
        )
        _save_debug_image(f"infobox_action_{target}_processed", processed)
        return None, processed

    bbox = _extract_action_line_bbox(data, target)
    # OCR coordinates are in the 2x-upscaled image space; scale back to
    # the original infobox coordinate system.
    if bbox is not None:
        bx, by, bw, bh = bbox
        # Save a tightly-cropped debug image of just the target-action line
        # region (in 2x space) so the debug PNG shows exactly what Tesseract
        # read rather than the entire context-menu crop.
        _save_debug_image(f"infobox_action_{target}_processed", processed[by : by + bh, bx : bx + bw])
        # Use floor division for position fields (pixel origins round down) and
        # ceiling division for size fields so odd-pixel 2x extents round up
        # rather than truncating, preserving the full original-space extent.
        bbox = (
            bx // 2,
            by // 2,
            max(1, (bw + 1) // 2),
            max(1, (bh + 1) // 2),
        )
    else:
        _save_debug_image(f"infobox_action_{target}_processed", processed)
    return bbox, processed


def ocr_title_strip(title_strip_bgr: np.ndarray) -> InfoboxOcrResult:
    """
    OCR a pre-cropped infobox title strip to derive the item title.
    """
    if title_strip_bgr.size == 0:
        return InfoboxOcrResult(
            item_name="",
            raw_item_text="",
            processed=np.zeros((1, 1), dtype=np.uint8),
            preprocess_time=0.0,
            ocr_time=0.0,
            source="infobox",
            ocr_failed=True,
        )
    global _last_ocr_result, _last_roi_hash
    # Hash the raw BGR input so that two different raw strips that happen to produce
    # the same binarized image are not incorrectly served each other's result.
    roi_hash = _hash_roi(title_strip_bgr)
    preprocess_start = time.perf_counter()
    processed = preprocess_for_ocr(title_strip_bgr)
    _save_debug_image("infobox_processed", processed)
    preprocess_time = time.perf_counter() - preprocess_start
    if _last_roi_hash == roi_hash and _last_ocr_result is not None:
        item_name, raw_item_text = _last_ocr_result
        return InfoboxOcrResult(
            item_name=item_name,
            raw_item_text=raw_item_text,
            processed=processed,
            preprocess_time=preprocess_time,
            ocr_time=0.0,
            source="infobox",
        )

    ocr_time = 0.0
    try:
        ocr_start = time.perf_counter()
        raw_text = image_to_string(processed, single_line=True)
        ocr_time = time.perf_counter() - ocr_start
    except Exception as exc:  # pragma: no cover - OCR backend dependent
        _last_roi_hash = None  # invalidate cache so next call does not re-serve stale result
        print(
            f"[vision_ocr] ocr_backend image_to_string failed for infobox title strip; "
            f"falling back to empty OCR result. error={exc}",
            flush=True,
        )
        return InfoboxOcrResult(
            item_name="",
            raw_item_text="",
            processed=processed,
            preprocess_time=preprocess_time,
            ocr_time=ocr_time,
            source="infobox",
            ocr_failed=True,
        )

    match_result = match_item_name_result(raw_text)
    raw_item_text = match_result.cleaned_text
    item_name = match_result.chosen_name
    if item_name:
        _last_roi_hash = roi_hash
        _last_ocr_result = (item_name, raw_item_text)
    return InfoboxOcrResult(
        item_name=item_name,
        raw_item_text=raw_item_text,
        processed=processed,
        preprocess_time=preprocess_time,
        ocr_time=ocr_time,
        source="infobox",
    )


def ocr_infobox(infobox_bgr: np.ndarray) -> InfoboxOcrResult:
    """
    OCR the infobox title strip once to derive the item title.
    """
    _save_debug_image("infobox_raw", infobox_bgr)
    title_strip_bgr = _crop_title_strip(infobox_bgr)
    _save_debug_image("infobox_title_raw", title_strip_bgr)
    return ocr_title_strip(title_strip_bgr)


def build_skip_unlisted_corpus_image(infobox_bgr: np.ndarray, *, from_context_menu: bool) -> np.ndarray:
    if from_context_menu:
        return np.ascontiguousarray(infobox_bgr)
    return np.ascontiguousarray(_crop_title_strip(infobox_bgr))


def ocr_context_menu(context_crop_bgr: np.ndarray) -> InfoboxOcrResult:
    """
    OCR a dark context-menu crop to extract the item name.

    Unlike ``ocr_infobox``, this does not strip to the title row.  Instead it
    searches every text line top-to-bottom for one that fuzzy-matches a known
    item name via ``match_item_name``.  This handles menus that mix action
    labels ("Move to Backpack", "Sell", "Recycle") with the item title.
    """
    if context_crop_bgr.size == 0:
        return InfoboxOcrResult(
            item_name="",
            raw_item_text="",
            processed=np.zeros((1, 1), dtype=np.uint8),
            preprocess_time=0.0,
            ocr_time=0.0,
            source="context_menu",
            ocr_failed=True,
        )
    preprocess_start = time.perf_counter()
    _save_debug_image("ctx_menu_raw", context_crop_bgr)
    processed = preprocess_for_ocr(context_crop_bgr, restrict_otsu_to_left=True)
    _save_debug_image("ctx_menu_processed", processed)

    preprocess_time = time.perf_counter() - preprocess_start

    ocr_time = 0.0
    try:
        ocr_start = time.perf_counter()
        data = image_to_data(processed)
        ocr_time = time.perf_counter() - ocr_start
    except Exception as exc:  # pragma: no cover - OCR backend failure path
        print(
            f"[vision_ocr] ocr_backend image_to_data failed for context menu; "
            f"falling back to empty OCR result. error={exc}",
            flush=True,
        )
        return InfoboxOcrResult(
            item_name="",
            raw_item_text="",
            processed=processed,
            preprocess_time=preprocess_time,
            ocr_time=ocr_time,
            source="context_menu",
            ocr_failed=True,
        )

    # Group words into lines keyed by (page, block, par, line).
    texts = data.get("text", [])
    groups: defaultdict[Tuple[int, int, int, int], List[int]] = defaultdict(list)
    for i, raw_text in enumerate(texts):
        cleaned = clean_ocr_text(raw_text or "")
        if not cleaned:
            continue
        key = (
            int(data["page_num"][i]),
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        groups[key].append(i)

    def _line_top(indices: List[int]) -> float:
        return min(float(data["top"][i]) for i in indices)

    # Known action-button labels that are never item names.  Lines whose
    # lowercased text starts with one of these are skipped before fuzzy
    # matching so that left-clipped fragments (e.g. "it Stack" from "Split
    # Stack") cannot accidentally match a real item name.
    _ACTION_PREFIXES = (
        "split stack",
        "move to backpack",
        "move to safe pocket",
        "inspect",
        "sell",
        "recycle",
        "drop",
        "equip",
        "unequip",
        "unavailable",
        "detach mods",
        "repair",
        "upgrade",
    )

    item_name = ""
    raw_item_text = ""
    for key in sorted(groups.keys(), key=lambda k: _line_top(groups[k])):
        indices = sorted(groups[key])
        raw_parts = [(data["text"][i] or "").strip() for i in indices if data["text"][i]]
        cleaned_parts = [clean_ocr_text(p) for p in raw_parts]
        line_text = " ".join(p for p in cleaned_parts if p).strip()
        line_lower = line_text.lower()
        # Strip leading non-alpha chars (e.g. OCR'd game icons) before
        # checking action prefixes.
        stripped_lower = re.sub(r"^[^a-z]+", "", line_lower)
        if any(line_lower.startswith(p) or stripped_lower.startswith(p) for p in _ACTION_PREFIXES):
            continue
        # Skip very short fragments (stash quantity labels like "1", "3") —
        # they false-match item names via partial_ratio in WRatio.  Threshold
        # is 3 so that any 3-char item name can still pass; the coverage guard
        # below catches short noise that slips through (e.g. "arc" at 3 chars
        # matches "Arc Alloy" at 33% coverage, well below the 60% floor).
        if len(line_text) < 3:
            continue
        result = match_item_name_result(line_text)
        if result.matched_name is not None:
            # Guard against WRatio partial_ratio false positives: a fragment
            # like "ARC A" (5 chars) matches "Arc Alloy" (9 chars) at 100%
            # via partial substring matching.  Require the OCR text to cover
            # at least 60% of the matched name length so short noise strings
            # are rejected even when they exceed the minimum-length guard.
            # Use line_text (single-cleaned) rather than result.cleaned_text
            # (doubly-cleaned) so punctuation stripping doesn't shrink the
            # measured length and over-reject valid short names.
            coverage = len(line_text) / max(1, len(result.matched_name))
            if coverage < 0.6:
                continue
            item_name = result.chosen_name
            raw_item_text = " ".join(p for p in raw_parts if p).strip()
            break

    return InfoboxOcrResult(
        item_name=item_name,
        raw_item_text=raw_item_text,
        processed=processed,
        preprocess_time=preprocess_time,
        ocr_time=ocr_time,
        source="context_menu",
    )


def ocr_item_name(roi_bgr: np.ndarray) -> str:
    """
    OCR the item name from the pre-cropped title ROI.
    """
    if roi_bgr.size == 0:
        return ""

    global _last_ocr_result, _last_roi_hash
    roi_hash = _hash_roi(roi_bgr)
    if _last_roi_hash == roi_hash and _last_ocr_result is not None:
        return _last_ocr_result[0]

    processed = preprocess_for_ocr(roi_bgr)
    try:
        raw = image_to_string(processed, single_line=True)
    except Exception as exc:  # pragma: no cover - OCR backend dependent
        _last_roi_hash = None  # invalidate cache so next call does not re-serve stale result
        print(
            f"[vision_ocr] ocr_backend image_to_string failed for item name; falling back to empty result. error={exc}",
            flush=True,
        )
        return ""

    item_name = match_item_name(raw)
    if item_name:
        _last_roi_hash = roi_hash
        _last_ocr_result = (item_name, raw)

    return item_name


def ocr_inventory_count(roi_bgr: np.ndarray) -> Tuple[Optional[int], str]:
    """
    OCR the "items in stash" label and return (count, raw_text).
    """
    if roi_bgr.size == 0:
        return None, ""

    _save_debug_image("inventory_count_raw", roi_bgr)
    processed = preprocess_for_ocr(roi_bgr)
    _save_debug_image("inventory_count_processed", processed)

    try:
        raw = image_to_string(processed)
    except Exception as exc:  # pragma: no cover - OCR backend dependent
        print(
            f"[vision_ocr] ocr_backend image_to_string failed for inventory count: {exc}",
            flush=True,
        )
        return None, ""

    cleaned = (raw or "").replace("\n", " ").strip()
    # The label reads "N/M" (current/capacity). Extract N from that pattern first so
    # that a stash-icon glyph OCR'd before the digits (e.g. "8 197/232") does not
    # cause digits[0] to return the icon's value instead of the item count.
    m = re.search(r"(\d+)/\d+", cleaned)
    if m:
        return int(m.group(1)), cleaned

    digits = re.findall(r"\d+", cleaned)
    if not digits:
        return None, cleaned

    # Skip a likely stash-icon noise digit: a single-digit prefix followed by a
    # multi-digit number (e.g. "8 197" → use 197, not 8).
    if len(digits) >= 2 and len(digits[0]) == 1 and len(digits[1]) > 1:
        count = int(digits[1])
    else:
        count = int(digits[0])

    return count, cleaned
