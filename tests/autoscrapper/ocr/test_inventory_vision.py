"""Tests for ocr/inventory_vision.py — pure functions and bug-fix regressions."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Stub heavy platform deps before any autoscrapper import
# ---------------------------------------------------------------------------
sys.modules.setdefault("pywinctl", MagicMock())
sys.modules.setdefault("pymonctl", MagicMock())
sys.modules.setdefault("pynput", MagicMock())
sys.modules.setdefault("pynput.keyboard", MagicMock())
sys.modules.setdefault("pynput.mouse", MagicMock())

from autoscrapper.ocr.inventory_vision import (  # noqa: E402
    ItemNameMatchResult,
    _extract_cropped_title_from_data,
    _extract_title_from_data,
    _odd,
    find_infobox_with_debug,
    find_context_menu_crop,
    isolate_menu_panel,
    match_item_name_result,
    ocr_inventory_count,
    preprocess_for_ocr,
    reset_ocr_caches,
    title_roi,
)
import autoscrapper.ocr.inventory_vision as _vision  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ocr_data(*words):
    """Build a Tesseract-style data dict from (text, conf, top, height) tuples.

    By default all words share page/block/par/line = 1 so they form a single
    group. Pass a 5th tuple value to override line_num for multi-line tests.
    """
    keys = ["text", "conf", "top", "height", "page_num", "block_num", "par_num", "line_num"]
    result = {k: [] for k in keys}
    for word in words:
        if len(word) == 4:
            text, conf, top, height = word
            line_num = 1
        else:
            text, conf, top, height, line_num = word
        result["text"].append(text)
        result["conf"].append(conf)
        result["top"].append(top)
        result["height"].append(height)
        result["page_num"].append(1)
        result["block_num"].append(1)
        result["par_num"].append(1)
        result["line_num"].append(line_num)
    return result


def _match_result(
    cleaned_text: str,
    *,
    chosen_name: str | None = None,
    matched_name: str | None = None,
    threshold: int = 75,
) -> ItemNameMatchResult:
    return ItemNameMatchResult(
        cleaned_text=cleaned_text,
        chosen_name=cleaned_text if chosen_name is None else chosen_name,
        matched_name=matched_name,
        threshold=threshold,
    )


def _solid_bgr(h, w, color=(128, 128, 128)):
    img = np.full((h, w, 3), color, dtype=np.uint8)
    return img


# ---------------------------------------------------------------------------
# preprocess_for_ocr — Bug 1 & 2 regression
# ---------------------------------------------------------------------------


class TestPreprocessForOcr:
    def test_zero_size_raises_value_error(self):
        """Bug 1: zero-size input must raise ValueError before cv2 crashes."""
        with pytest.raises(ValueError, match="empty input"):
            preprocess_for_ocr(np.zeros((0, 10, 3), dtype=np.uint8))

    def test_zero_height_raises_value_error(self):
        with pytest.raises(ValueError, match="empty input"):
            preprocess_for_ocr(np.zeros((10, 0, 3), dtype=np.uint8))

    def test_output_is_2x_input_size(self):
        img = _solid_bgr(20, 40)
        out = preprocess_for_ocr(img)
        assert out.shape == (40, 80), f"expected (40,80), got {out.shape}"

    def test_output_is_binary(self):
        img = _solid_bgr(20, 40)
        out = preprocess_for_ocr(img)
        unique = set(np.unique(out).tolist())
        assert unique.issubset({0, 255}), f"non-binary values: {unique - {0, 255}}"

    def test_restrict_otsu_to_left_normal_image(self):
        """restrict_otsu_to_left should not crash on a normal-width image."""
        img = _solid_bgr(20, 40)
        out = preprocess_for_ocr(img, restrict_otsu_to_left=True)
        assert out.shape == (40, 80)

    def test_restrict_otsu_to_left_width_one_input(self):
        """Bug 2: width-1 input (→ w_g=2, half=1) must not crash."""
        img = _solid_bgr(20, 1)
        out = preprocess_for_ocr(img, restrict_otsu_to_left=True)
        assert out.shape == (40, 2)


# ---------------------------------------------------------------------------
# title_roi — pure coordinate math
# ---------------------------------------------------------------------------


class TestTitleRoi:
    def test_returns_same_x_y(self):
        rect = (10, 20, 200, 100)
        x, y, *_ = title_roi(rect)
        assert x == 10
        assert y == 20

    def test_width_preserved(self):
        rect = (0, 0, 300, 80)
        _, _, w, _ = title_roi(rect)
        assert w == 300

    def test_height_is_fraction_of_infobox_height(self):
        from autoscrapper.ocr.inventory_vision import TITLE_HEIGHT_REL

        _, _, _, h_title = title_roi((0, 0, 100, 100))
        assert h_title == max(1, int(TITLE_HEIGHT_REL * 100))

    def test_minimum_height_is_one(self):
        """Very short infobox must still produce height >= 1."""
        _, _, _, h = title_roi((0, 0, 100, 1))
        assert h >= 1


# ---------------------------------------------------------------------------
# _extract_title_from_data — coordinate-space regression (Bug 3 from review 2)
# ---------------------------------------------------------------------------


class TestExtractTitleFromData:
    """Tesseract returns coords in 2x-upscaled space; image_height must match."""

    def test_word_in_upper_half_included(self):
        """A word whose center_y is within the top fraction is kept."""
        # 2x image height = 40; top_fraction = 0.5 → cutoff = 20
        # Word at top=5, height=10 → center_y = 10 ≤ 20 → included
        data = _make_ocr_data(("Hello", 90, 5, 10))
        with patch.object(
            _vision,
            "match_item_name_result",
            return_value=_match_result("Hello", chosen_name="Hello", matched_name="Hello"),
        ):
            _, raw = _extract_title_from_data(data, image_height=40, top_fraction=0.5)
        assert "Hello" in raw

    def test_word_in_lower_half_excluded(self):
        """A word whose center_y exceeds the cutoff is filtered out."""
        # 2x image height = 40; top_fraction = 0.5 → cutoff = 20
        # Word at top=16, height=10 → center_y = 21 > 20 → excluded
        data = _make_ocr_data(("Hidden", 90, 16, 10))
        with patch.object(
            _vision,
            "match_item_name_result",
            return_value=_match_result("", chosen_name=""),
        ):
            _, raw = _extract_title_from_data(data, image_height=40, top_fraction=0.5)
        assert "Hidden" not in raw

    def test_2x_height_keeps_word_original_height_would_drop(self):
        """Demonstrate why image_height must be the 2x height.

        Word at top=8, height=10 → center_y = 13.
        With 2x height (40) and top_fraction 0.5: cutoff=20 → included.
        With original height (20) and top_fraction 0.5: cutoff=10 → excluded.
        Passing processed.shape[0] (2x) is therefore the correct behaviour.
        """
        data = _make_ocr_data(("Arc", 90, 8, 10))
        with patch.object(
            _vision,
            "match_item_name_result",
            return_value=_match_result("Arc", chosen_name="Arc", matched_name="Arc"),
        ):
            _, raw_2x = _extract_title_from_data(data, image_height=40, top_fraction=0.5)
            _, raw_orig = _extract_title_from_data(data, image_height=20, top_fraction=0.5)
        assert "Arc" in raw_2x, "2x height should include word in lower portion"
        assert "Arc" not in raw_orig, "original height cutoff would incorrectly drop the word"

    def test_empty_data_returns_empty_strings(self):
        assert _extract_title_from_data({}, image_height=40) == ("", "")

    def test_no_texts_returns_empty_strings(self):
        data = _make_ocr_data()
        with patch.object(
            _vision,
            "match_item_name_result",
            return_value=_match_result("", chosen_name=""),
        ):
            result = _extract_title_from_data(data, image_height=40)
        assert result == ("", "")

    def test_stat_line_uses_lower_priority_known_item_fallback(self):
        data = _make_ocr_data(
            ("Damage", 95, 2, 8, 1),
            ("55", 95, 2, 8, 1),
            ("Arc Alloy", 80, 14, 8, 2),
        )

        def _fake_match(text: str) -> ItemNameMatchResult:
            if text == "Damage 55":
                return _match_result("Damage 55")
            if text == "Range 100":
                return _match_result("Range 100")
            if text == "Arc Alloy":
                return _match_result(
                    "Arc Alloy",
                    chosen_name="Arc Alloy",
                    matched_name="Arc Alloy",
                )
            raise AssertionError(f"unexpected OCR text: {text}")

        with patch.object(_vision, "match_item_name_result", side_effect=_fake_match):
            item_name, raw = _extract_title_from_data(data, image_height=120)

        assert item_name == "Arc Alloy"
        assert raw == "Arc Alloy"

    def test_unmatched_non_stat_line_does_not_trigger_fallback(self):
        data = _make_ocr_data(
            ("Arc Allov", 95, 2, 8, 1),
            ("Random Text", 80, 14, 8, 2),
        )

        def _fake_match(text: str) -> ItemNameMatchResult:
            if text == "Arc Allov":
                return _match_result("Arc Allov", chosen_name="Arc Allov")
            if text == "Random Text":
                return _match_result("Random Text", chosen_name="Random Text")
            raise AssertionError(f"unexpected OCR text: {text}")

        with patch.object(_vision, "match_item_name_result", side_effect=_fake_match):
            item_name, raw = _extract_title_from_data(data, image_height=120)

        assert item_name == "Arc Allov"
        assert raw == "Arc Allov"

    def test_fallback_skips_multiple_stat_lines_before_known_item(self):
        data = _make_ocr_data(
            ("Damage", 95, 2, 8, 1),
            ("55", 95, 2, 8, 1),
            ("Range", 90, 12, 8, 2),
            ("100", 90, 12, 8, 2),
            ("Arc Alloy", 80, 22, 8, 3),
        )

        def _fake_match(text: str) -> ItemNameMatchResult:
            if text == "Damage 55":
                return _match_result("Damage 55")
            if text == "Range 100":
                return _match_result("Range 100")
            if text == "Arc Alloy":
                return _match_result(
                    "Arc Alloy",
                    chosen_name="Arc Alloy",
                    matched_name="Arc Alloy",
                )
            raise AssertionError(f"unexpected OCR text: {text}")

        with patch.object(_vision, "match_item_name_result", side_effect=_fake_match):
            item_name, raw = _extract_title_from_data(data, image_height=120)

        assert item_name == "Arc Alloy"
        assert raw == "Arc Alloy"


# ---------------------------------------------------------------------------
# _extract_cropped_title_from_data — delegates with top_fraction=1.0
# ---------------------------------------------------------------------------


class TestExtractCroppedTitleFromData:
    def test_top_fraction_one_includes_all_words(self):
        """top_fraction=1.0 means the cutoff equals image_height — all words pass."""
        # center_y = top + height/2 = 30 + 5 = 35; image_height = 40; cutoff = 40 → passes
        data = _make_ocr_data(("Alloy", 90, 30, 10))
        with patch.object(
            _vision,
            "match_item_name_result",
            return_value=_match_result("Alloy", chosen_name="Alloy", matched_name="Alloy"),
        ):
            _, raw = _extract_cropped_title_from_data(data, image_height=40)
        assert "Alloy" in raw


# ---------------------------------------------------------------------------
# ocr_title_strip — cache does not store empty item_name (Bug 5 regression)
# ---------------------------------------------------------------------------


class TestOcrTitleStripCache:
    def _make_image(self):
        return _solid_bgr(30, 100)

    def test_empty_result_not_cached(self):
        """When item_name is empty, the cache must NOT be updated.

        A subsequent call with the same image must re-invoke image_to_data.
        """
        reset_ocr_caches()
        img = self._make_image()
        # no words → item_name will be ""

        with (
            patch.object(_vision, "image_to_string", return_value="") as mock_ocr,
            patch.object(
                _vision,
                "match_item_name_result",
                return_value=_match_result("", chosen_name=""),
            ),
        ):
            _vision.ocr_title_strip(img)
            _vision.ocr_title_strip(img)  # same image

        # Each ocr_title_strip call makes 3 image_to_string calls when empty:
        # 1. upscale
        # 2. no-upscale fallback
        # 3. inverted polarity fallback (T024)
        # 3 × 2 = 6.
        assert mock_ocr.call_count == 6, (
            "image_to_string called 6 times: 3 per invocation (upscale + no-upscale + inverted)"
        )

    def test_non_empty_result_is_cached(self):
        """When item_name is non-empty, the second call must use the cache."""
        reset_ocr_caches()
        img = self._make_image()

        with (
            patch.object(_vision, "image_to_string", return_value="FoundItem") as mock_ocr,
            patch.object(
                _vision,
                "match_item_name_result",
                return_value=_match_result(
                    "Arc Alloy",
                    chosen_name="Arc Alloy",
                    matched_name="Arc Alloy",
                ),
            ),
        ):
            _vision.ocr_title_strip(img)
            _vision.ocr_title_strip(img)  # same image — should hit cache

        assert mock_ocr.call_count == 1, "image_to_data should only be called once when result was cached"


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ocr_item_name — cache tests
# ---------------------------------------------------------------------------


class TestOcrItemNameCache:
    def _make_image(self):
        return _solid_bgr(30, 100)

    def test_empty_result_not_cached(self):
        reset_ocr_caches()
        img = self._make_image()

        with patch.object(_vision, "image_to_string", return_value="") as mock_ocr:
            _vision.ocr_item_name(img)
            _vision.ocr_item_name(img)

        assert mock_ocr.call_count == 2, "image_to_string should be called twice when the first result was empty"

    def test_non_empty_result_is_cached(self):
        reset_ocr_caches()
        img = self._make_image()

        with (
            patch.object(_vision, "image_to_string", return_value="FoundItem") as mock_ocr,
            patch.object(
                _vision,
                "match_item_name",
                return_value="Arc Alloy",
            ),
        ):
            _vision.ocr_item_name(img)
            _vision.ocr_item_name(img)

        assert mock_ocr.call_count == 1, "image_to_string should only be called once when result was cached"


# reset_ocr_caches
# ---------------------------------------------------------------------------


class TestResetOcrCaches:
    def test_clears_all_three_caches(self):
        # Prime the caches artificially
        _vision._last_roi_hash = b"fake"
        _vision._last_ocr_result = ("Item", "Item")
        _vision.rules_store._ITEM_NAMES = ("Item A", "Item B")

        reset_ocr_caches()

        assert _vision._last_roi_hash is None
        assert _vision._last_ocr_result is None
        assert _vision.rules_store._ITEM_NAMES is None


# ---------------------------------------------------------------------------
# enable_ocr_debug
# ---------------------------------------------------------------------------


class TestEnableOcrDebug:
    def test_enable_ocr_debug_success(self, tmp_path):
        """Test that enable_ocr_debug sets the debug directory and creates it."""
        debug_dir = tmp_path / "ocr_debug"
        original_dir = _vision._OCR_DEBUG_DIR
        try:
            _vision.enable_ocr_debug(debug_dir)
            assert _vision._OCR_DEBUG_DIR == debug_dir
            assert debug_dir.exists()
        finally:
            _vision._OCR_DEBUG_DIR = original_dir

    def test_enable_ocr_debug_mkdir_exception(self, capsys):
        """Test that an exception during directory creation is caught and handled."""
        from pathlib import Path

        mock_path = MagicMock(spec=Path)
        mock_path.mkdir.side_effect = OSError("Permission denied")

        # Use patch to isolate global state and verify it is cleared on failure
        with patch.object(_vision, "_OCR_DEBUG_DIR", Path("/tmp/dummy")):
            _vision.enable_ocr_debug(mock_path)
            assert _vision._OCR_DEBUG_DIR is None

        captured = capsys.readouterr()
        assert "[vision_ocr] failed to enable OCR debug dir: Permission denied" in captured.out


# ---------------------------------------------------------------------------
# ocr_inventory_count — regression tests for the phantom-digit fix
# ---------------------------------------------------------------------------


class TestOcrInventoryCount:
    """Tests for ocr_inventory_count() focusing on the N/M artifact-stripping logic."""

    def _call(self, ocr_text: str):
        """Call ocr_inventory_count with a real dummy image but mocked OCR output."""
        img = _solid_bgr(20, 80)
        with patch("autoscrapper.ocr.inventory_vision.image_to_string", return_value=ocr_text):
            return ocr_inventory_count(img)

    def test_normal_count(self):
        count, raw = self._call("197/232")
        assert count == 197
        assert "197/232" in raw

    def test_current_equals_capacity(self):
        """Full stash — current == capacity is valid."""
        count, _ = self._call("280/280")
        assert count == 280

    def test_phantom_leading_digit_stripped(self):
        """Regression: OCR reads '2251/280'; should recover to 251."""
        count, _ = self._call("2251/280")
        assert count == 251

    def test_artifact_not_stripped_when_same_digit_length(self, capsys):
        """'999/280': same digit length as capacity — no strip, returns None + logs."""
        count, _ = self._call("999/280")
        assert count is None
        out = capsys.readouterr().out
        assert "[vision_ocr] ocr_inventory_count: unrecoverable count" in out

    def test_artifact_not_stripped_when_two_surplus_digits(self, capsys):
        """'22251/280': two surplus digits — conservative, no strip, returns None."""
        count, _ = self._call("22251/280")
        assert count is None
        capsys.readouterr()  # consume log

    def test_no_slash_pattern_falls_through_to_digit_fallback(self):
        """No N/M pattern — falls through to digit extraction path."""
        count, _ = self._call("251")
        assert count == 251

    def test_empty_roi_returns_none(self):
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        count, raw = ocr_inventory_count(empty)
        assert count is None
        assert raw == ""

    def test_no_digits_returns_none(self):
        count, _ = self._call("no digits here")
        assert count is None


# ---------------------------------------------------------------------------
# find_context_menu_crop — right-edge geometry regression (Bug: title clipped)
# ---------------------------------------------------------------------------


class TestFindContextMenuCrop:
    """Regression tests ensuring the context-menu crop reaches far enough right.

    Root cause: _CONTEXT_MENU_X_OFFSET_NORM was 35/1920 (≈35 px at 1080p),
    so right edge = cell_center_x + 35.  Item titles like "MATRIARCH REACTOR"
    extend ~200-250 px past the cell centre — they were clipped, causing
    title-unreadable / UNAVAILABLE outcomes.

    Fix: X_OFFSET_NORM → 250/1920, WIDTH_NORM → 450/1920.
    The right edge must now be ≥ 200 px past cell_center_x.
    """

    _W = 1920
    _H = 1080

    def _solid(self):
        """Return a dark-panel-like 1920×1080 image so both brightness guards pass.

        The context-menu dark-fraction guard requires ≥20% of left-half pixels to
        be below gray 40.  Use a bimodal image: every 4th row is dark (value 20),
        remaining rows bright (value 100).  This gives ~25% dark pixels (≥20%)
        and a mean brightness of ~80 (≥40), matching the real context-menu UI.
        """
        img = np.full((self._H, self._W, 3), 100, dtype=np.uint8)
        img[::4, :] = 20  # every 4th row dark → ≈25% dark pixels
        return img

    def _crop(self, cx: int, cy: int):
        img = self._solid()
        return find_context_menu_crop(img, cx, cy)

    def test_right_edge_extends_at_least_200px_past_cell_centre(self):
        """Right edge of crop must be ≥ 200 px past cell_center_x."""
        cx, cy = 800, 540
        result = self._crop(cx, cy)
        assert result is not None, "crop should succeed on a bright image"
        x, _, w, _ = result
        right_edge = x + w
        assert right_edge >= cx + 200, (
            f"right edge {right_edge} is only {right_edge - cx} px past centre {cx}; title text will be clipped"
        )

    def test_right_edge_extends_at_least_200px_near_left_screen(self):
        """Same geometry holds when cell is near the left screen edge."""
        cx, cy = 200, 300
        result = self._crop(cx, cy)
        assert result is not None
        x, _, w, _ = result
        right_edge = x + w
        # Crop is clamped to screen, but must still extend past centre
        assert right_edge >= cx + 200 or right_edge == self._W, (
            "right edge must reach 200 px past centre or be clamped to screen width"
        )

    def test_crop_stays_within_image_bounds(self):
        """Crop rectangle must not exceed image dimensions."""
        for cx, cy in [(100, 100), (960, 540), (1800, 900)]:
            result = self._crop(cx, cy)
            if result is None:
                continue
            x, y, w, h = result
            assert x >= 0 and y >= 0
            assert x + w <= self._W
            assert y + h <= self._H

    def test_returns_none_on_dark_image(self):
        """Polarity guard: black image (mean < 40) should return None."""
        dark = np.zeros((self._H, self._W, 3), dtype=np.uint8)
        result = find_context_menu_crop(dark, 800, 540)
        assert result is None, "dark crop should be rejected by brightness guard"

    def test_crop_width_large_enough_for_long_titles(self):
        """Crop width must be ≥ 400 px (at 1920) to fit 'MATRIARCH REACTOR' text."""
        result = self._crop(800, 540)
        assert result is not None
        _, _, w, _ = result
        assert w >= 400, f"crop width {w} is too narrow for long item titles"

    def test_shifts_left_at_right_screen_edge(self):
        """Crop shifts left if it would overflow the right edge, preserving its width."""
        cx = self._W - 50
        cy = 540
        result = self._crop(cx, cy)
        assert result is not None
        x, _, w, _ = result
        assert x + w == self._W, "crop right edge should align with screen right edge"
        expected_w = int(round(_vision._CONTEXT_MENU_WIDTH_NORM * self._W))
        assert w == expected_w, "crop width must be preserved despite shifting"

    def test_shifts_up_at_bottom_screen_edge(self):
        """Crop shifts up if it would overflow the bottom edge, preserving its height."""
        cx = 800
        cy = self._H - 50
        result = self._crop(cx, cy)
        assert result is not None
        _, y, _, h = result
        assert y + h == self._H, "crop bottom edge should align with screen bottom edge"
        expected_h = int(round(_vision._CONTEXT_MENU_HEIGHT_NORM * self._H))
        assert h == expected_h, "crop height must be preserved despite shifting"

    def test_returns_none_if_crop_too_small(self):
        """If the input image is too small to yield min_dim, returns None."""
        tiny_img = np.full((50, 50, 3), 100, dtype=np.uint8)
        result = find_context_menu_crop(tiny_img, 25, 25)
        assert result is None, "should return None when crop dims < min_dim"

    def test_returns_none_on_low_dark_fraction(self):
        """Left half of crop must have >= 20% dark pixels (sidebar icons), else None."""
        bright_img = np.full((self._H, self._W, 3), 200, dtype=np.uint8)
        result = find_context_menu_crop(bright_img, 800, 540)
        assert result is None, "bright crop without dark sidebar fraction should be rejected"


# ---------------------------------------------------------------------------
# isolate_menu_panel — panel bounding-rect detection
# ---------------------------------------------------------------------------


class TestIsolateMenuPanel:
    """Unit tests for isolate_menu_panel().

    The function must find the largest white/cream rectangle (context menu
    panel) in a mixed crop and return its bounding rect, or None when no
    qualifying panel is present.
    """

    def _make_mixed_crop(
        self,
        crop_w: int = 450,
        crop_h: int = 450,
        panel_x: int = 80,
        panel_w: int = 220,
    ) -> np.ndarray:
        """Synthetic crop: dark background + bright white panel + dark sidebar.

        Layout mirrors real game crop:
        - Left strip (0..panel_x): dark sidebar area (value 30)
        - Panel (panel_x..panel_x+panel_w): white/cream background (value 235)
          with a few dark text-like pixels (value 40) scattered inside
        - Right strip (panel_x+panel_w..crop_w): dark inventory grid (value 35)
        """
        img = np.full((crop_h, crop_w, 3), 30, dtype=np.uint8)
        # Bright panel region
        img[:, panel_x : panel_x + panel_w] = 235
        # Simulate dark text rows inside the panel (doesn't break bright detection)
        for row in [30, 90, 150, 210, 270]:
            img[row, panel_x + 10 : panel_x + panel_w - 10] = 40
        # Small bright spot in sidebar (10x10) — must be rejected
        img[20:30, 5:15] = 240
        return img

    def test_returns_rect_for_bright_panel_on_mixed_background(self):
        """Panel must be detected and rect must overlap the known bright region."""
        img = self._make_mixed_crop()
        result = isolate_menu_panel(img)
        assert result is not None, "should detect the bright menu panel"
        x, _y, w, _h = result
        # Rect must overlap the panel column range (80..300)
        assert x < 300 and x + w > 80, f"returned rect x={x} w={w} does not overlap panel columns 80-300"

    def test_returns_none_for_uniform_dark_image(self):
        """No bright panel in a uniform dark image — expect None."""
        img = np.full((450, 450, 3), 30, dtype=np.uint8)
        assert isolate_menu_panel(img) is None

    def test_returns_none_for_too_small_bright_region(self):
        """A bright rect covering < 15% of crop area must not be returned."""
        crop_h, crop_w = 450, 450
        img = np.full((crop_h, crop_w, 3), 30, dtype=np.uint8)
        # 50x50 = 2500 px² < 15% of 202500 = 30375
        img[10:60, 10:60] = 240
        assert isolate_menu_panel(img) is None

    def test_returns_none_for_empty_array(self):
        """Empty array must return None without raising."""
        img = np.zeros((0, 0, 3), dtype=np.uint8)
        assert isolate_menu_panel(img) is None

    def test_rect_within_crop_bounds(self):
        """Returned rect must be fully inside the input image."""
        img = self._make_mixed_crop()
        result = isolate_menu_panel(img)
        if result is None:
            pytest.skip("panel not detected — bounds check irrelevant")
        x, y, w, h = result
        crop_h, crop_w = img.shape[:2]
        assert x >= 0 and y >= 0
        assert x + w <= crop_w
        assert y + h <= crop_h

    def test_returns_none_for_thin_horizontal_strip(self):
        """A bright rect that is too wide/short (aspect > 3.0) must not be returned."""
        img = np.zeros((100, 400, 3), dtype=np.uint8)
        img[20:80, 50:350] = (220, 220, 220)  # bw=300, bh=60, area=18000, aspect=5.0
        assert isolate_menu_panel(img) is None

    def test_returns_none_for_thin_vertical_strip(self):
        """A bright rect that is too tall/narrow (aspect < 0.3) must not be returned."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[10:90, 40:60] = (220, 220, 220)  # bw=20, bh=80, area=1600, aspect=0.25
        assert isolate_menu_panel(img) is None

    def test_returns_none_for_short_panel(self):
        """A bright rect covering < 50% of crop height must not be returned."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[20:60, 20:60] = (220, 220, 220)
        assert isolate_menu_panel(img) is None


# ---------------------------------------------------------------------------
# match_item_name_result — case-insensitivity regression
# ---------------------------------------------------------------------------


class TestMatchItemNameCaseInsensitive:
    """Game renders context-menu titles in ALL CAPS; rules catalog stores Title Case.

    fuzz.WRatio is case-sensitive, so without processor=str.lower the raw OCR
    string scores ~17 against its canonical name and falls below the 75 threshold.
    These samples all come from the ocr_debug/ctx_menu_lines_fail corpus.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("MATRIARCH REACTOR", "Matriarch Reactor"),
            ("FABRIC", "Fabric"),
            ("HORNET DRIVER", "Hornet Driver"),
            ("BOMBARDIER CELL", "Bombardier Cell"),
            ("DURABLE CLOTH", "Durable Cloth"),
            ("ARC ALLOY", "ARC Alloy"),
            # Icon-bleed prefix noise must still resolve once case is normalized
            ("ry MATRIARCH REACTOR", "Matriarch Reactor"),
            ("50 50 FABRIC", "Fabric"),
            ("4 Is 7 HORNET DRIVER", "Hornet Driver"),
            ("ee: BOMBARDIER CELL", "Bombardier Cell"),
            ("7 Mn DURABLE CLOTH", "Durable Cloth"),
            ("Naw ARC ALLOY", "ARC Alloy"),
        ],
    )
    def test_all_caps_title_matches_catalog(self, raw: str, expected: str) -> None:
        result = match_item_name_result(raw)
        assert result.matched_name == expected, f"raw={raw!r} expected={expected!r} got={result.matched_name!r}"


# ---------------------------------------------------------------------------
# _odd - Bug/Edge Case regression
# ---------------------------------------------------------------------------


class TestOdd:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (2, 3),
            (4, 5),
            (1, 1),
            (3, 3),
            (0, 1),
            (-2, -1),
            (-4, -3),
            (-1, -1),
            (-3, -3),
        ],
    )
    def test_odd_logic(self, value: int, expected: int) -> None:
        assert _odd(value) == expected


from autoscrapper.ocr.inventory_vision import isolate_dark_title_panel  # noqa: E402


# ---------------------------------------------------------------------------
# isolate_dark_title_panel — dark title-band detection
# ---------------------------------------------------------------------------


class TestIsolateDarkTitlePanel:
    """Unit tests for isolate_dark_title_panel().

    The function must find the dark header rectangle in the top half of a
    context-menu crop and return its bounding rect, or None when none exists.
    """

    def _make_crop_with_dark_title(
        self,
        crop_w: int = 450,
        crop_h: int = 450,
        title_x: int = 0,
        title_w: int = 450,
        title_h: int = 60,
    ) -> np.ndarray:
        """Bright background with a dark horizontal title band at the top."""
        img = np.full((crop_h, crop_w, 3), 220, dtype=np.uint8)
        img[:title_h, title_x : title_x + title_w] = 40
        return img

    def test_detects_dark_title_band_at_top(self) -> None:
        """A dark band in the top half must be detected and returned."""
        img = self._make_crop_with_dark_title()
        result = isolate_dark_title_panel(img)
        assert result is not None, "should detect the dark title band"

    def test_returned_rect_overlaps_dark_region(self) -> None:
        """Returned rect must overlap the known dark title region."""
        img = self._make_crop_with_dark_title(title_x=0, title_w=450, title_h=60)
        result = isolate_dark_title_panel(img)
        assert result is not None
        _x, y, _w, h = result
        assert y < 60 and y + h > 0, f"rect y={y} h={h} does not overlap top 60px"

    def test_returns_none_for_uniform_bright_image(self) -> None:
        """No dark panel in a uniform bright image — expect None."""
        img = np.full((450, 450, 3), 200, dtype=np.uint8)
        assert isolate_dark_title_panel(img) is None

    def test_dark_band_in_bottom_half_not_detected(self) -> None:
        """Dark rect only in the bottom half must not be returned."""
        img = np.full((400, 450, 3), 200, dtype=np.uint8)
        img[250:310, :] = 40  # dark band in lower half only
        assert isolate_dark_title_panel(img) is None

    def test_returns_none_for_empty_array(self) -> None:
        """Empty array must return None without raising."""
        img = np.zeros((0, 0, 3), dtype=np.uint8)
        assert isolate_dark_title_panel(img) is None

    def test_rect_within_crop_bounds(self) -> None:
        """Returned rect must be fully inside the input image."""
        img = self._make_crop_with_dark_title()
        result = isolate_dark_title_panel(img)
        if result is None:
            pytest.skip("panel not detected — bounds check irrelevant")
        x, y, w, h = result
        crop_h, crop_w = img.shape[:2]
        assert x >= 0 and y >= 0
        assert x + w <= crop_w
        assert y + h <= crop_h


# ---------------------------------------------------------------------------
# preprocess_for_ocr — new kwargs: apply_clahe, robust_polarity, close_gaps
# ---------------------------------------------------------------------------


class TestPreprocessForOcrNewKwargs:
    """Regression tests for the new kwargs added to preprocess_for_ocr."""

    def _white_text_on_black(self, h: int = 40, w: int = 200) -> np.ndarray:
        """White letters (value 240) on black (value 0) — inverted polarity."""
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[8:32, 10:190] = 240
        return img

    def _black_text_on_white(self, h: int = 40, w: int = 200) -> np.ndarray:
        """Black letters (value 10) on white (value 245) — correct polarity."""
        img = np.full((h, w, 3), 245, dtype=np.uint8)
        img[8:32, 10:190] = 10
        return img

    def test_apply_clahe_produces_valid_binary(self) -> None:
        """apply_clahe=True must not crash and must return a 2D binary image."""
        img = self._black_text_on_white()
        result = preprocess_for_ocr(img, apply_clahe=True)
        assert result.ndim == 2
        assert set(np.unique(result)).issubset({0, 255})

    def test_apply_clahe_false_still_works(self) -> None:
        """apply_clahe=False must still return a valid binary image."""
        img = self._black_text_on_white()
        result = preprocess_for_ocr(img, apply_clahe=False)
        assert result.ndim == 2
        assert set(np.unique(result)).issubset({0, 255})

    def test_robust_polarity_inverts_white_on_black(self) -> None:
        """robust_polarity=True must produce dark-on-light for white-on-black input."""
        img = self._white_text_on_black()
        result = preprocess_for_ocr(img, robust_polarity=True)
        unique, counts = np.unique(result, return_counts=True)
        majority = unique[np.argmax(counts)]
        assert majority == 255, f"expected white background after polarity fix, got majority={majority}"

    def test_robust_polarity_false_preserves_legacy_behavior(self) -> None:
        """robust_polarity=False must not crash and must return a valid binary."""
        img = self._black_text_on_white()
        result = preprocess_for_ocr(img, robust_polarity=False)
        assert result.ndim == 2
        assert set(np.unique(result)).issubset({0, 255})

    def test_close_gaps_with_upscale(self) -> None:
        """close_gaps=True + upscale=True must not crash and must return valid binary."""
        img = self._black_text_on_white()
        result = preprocess_for_ocr(img, close_gaps=True, upscale=True)
        assert result.ndim == 2
        assert set(np.unique(result)).issubset({0, 255})

    def test_close_gaps_skipped_without_upscale(self) -> None:
        """close_gaps=True but upscale=False must still return a valid binary."""
        img = self._black_text_on_white()
        result = preprocess_for_ocr(img, close_gaps=True, upscale=False)
        assert result.ndim == 2
        assert set(np.unique(result)).issubset({0, 255})


class TestFindInfoboxWithDebug:
    """Tests for the internal find_infobox_with_debug function."""

    def test_empty_image_returns_early(self) -> None:
        empty_image = np.array([])
        result = find_infobox_with_debug(empty_image)

        assert result.rect is None
        assert result.failure_reason == "empty_image"
        assert result.bbox_method is None
        assert result.contour_count == 0
        assert result.candidate_count == 0

    def test_no_contours_returns_early(self) -> None:
        # Pure black image, far from INFOBOX_COLOR_BGR
        black_image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = find_infobox_with_debug(black_image)

        assert result.rect is None
        assert result.failure_reason == "no_contours"
        assert result.bbox_method is None
        assert result.contour_count == 0
        assert result.candidate_count == 0

    def test_no_scored_contours_returns_early(self) -> None:
        # Black image with a tiny 10x10 square of the infobox color.
        # This will create a contour, but area is 100, which is < INFOBOX_MIN_AREA (1000).
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        infobox_color = _vision.INFOBOX_COLOR_BGR
        image[10:20, 10:20] = infobox_color

        result = find_infobox_with_debug(image)

        assert result.rect is None
        assert result.failure_reason == "no_scored_contours"
        assert result.bbox_method is None
        assert result.contour_count > 0
        assert result.candidate_count == 0

    @patch("autoscrapper.ocr.inventory_vision._dominant_edge_bbox", return_value=None)
    @patch("autoscrapper.ocr.inventory_vision._percentile_bbox_from_filled_contour", return_value=None)
    def test_percentile_fallback_failed_returns_early(
        self,
        mock_percentile_bbox: MagicMock,
        mock_dominant_edge: MagicMock,
    ) -> None:
        # Create an image that will yield at least one valid contour > INFOBOX_MIN_AREA
        # to pass the "no_scored_contours" check.
        # INFOBOX_MIN_AREA is 1000, so a 40x40 square area = 1600.
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        infobox_color = _vision.INFOBOX_COLOR_BGR
        image[10:50, 10:50] = infobox_color

        result = find_infobox_with_debug(image)

        assert result.rect is None
        assert result.failure_reason == "percentile_fallback_failed"
        assert result.bbox_method is None
        assert result.contour_count > 0
        assert result.candidate_count > 0
        mock_dominant_edge.assert_called_once()
        mock_percentile_bbox.assert_called_once()
