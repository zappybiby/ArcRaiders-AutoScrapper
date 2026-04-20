"""OCR regression tests against captured fixture images.

Fixtures live in tests/fixtures/ocr/. Each fixture is a pair:
  <slug>.png   — source image cropped to the infobox title area
  <slug>.json  — sidecar: {"expected_name": "...", "source": "ocr_debug", ...}

Add fixtures with:
    uv run python scripts/capture_ocr_fixture.py <ocr_debug_image> "<expected name>"

The suite is skipped automatically when no fixtures have been captured yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ocr"


def _collect_fixtures() -> list[tuple[Path, str]]:
    """Return [(image_path, expected_name)] for every sidecar found."""
    fixtures: list[tuple[Path, str]] = []
    for sidecar in sorted(FIXTURES_DIR.glob("*.json")):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        expected_name = data.get("expected_name")
        if not isinstance(expected_name, str) or not expected_name:
            continue
        image_path = sidecar.with_suffix(".png")
        if not image_path.exists():
            continue
        fixtures.append((image_path, expected_name))
    return fixtures


_FIXTURES = _collect_fixtures()


@pytest.mark.skipif(not _FIXTURES, reason="no OCR fixtures captured yet — run scripts/capture_ocr_fixture.py")
@pytest.mark.parametrize("image_path,expected_name", _FIXTURES, ids=[p.stem for p, _ in _FIXTURES])
def test_ocr_fixture_matches_expected(image_path: Path, expected_name: str) -> None:
    """OCR pipeline on a fixture image must match the expected item name."""
    pytest.importorskip("tesserocr", reason="tesserocr not installed")

    from autoscrapper.ocr.inventory_vision import match_item_name_result
    from autoscrapper.ocr.tesseract import image_to_string, initialize_ocr

    initialize_ocr()

    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        pytest.skip(f"could not load fixture image: {image_path}")
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    raw_text = image_to_string(img_rgb)
    result = match_item_name_result(raw_text)

    assert result.matched_name == expected_name, (
        f"fixture '{image_path.stem}': expected '{expected_name}', "
        f"got matched_name='{result.matched_name}' "
        f"(raw='{raw_text.strip()}', cleaned='{result.cleaned_text}', "
        f"threshold={result.threshold})"
    )


@pytest.mark.skipif(not _FIXTURES, reason="no OCR fixtures captured yet")
def test_all_fixtures_have_valid_sidecars() -> None:
    """Every .png fixture must have a valid sidecar with expected_name."""
    errors: list[str] = []
    for image_path in sorted(FIXTURES_DIR.glob("*.png")):
        sidecar = image_path.with_suffix(".json")
        if not sidecar.exists():
            errors.append(f"{image_path.name}: missing sidecar {sidecar.name}")
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{sidecar.name}: invalid JSON — {exc}")
            continue
        if not isinstance(data.get("expected_name"), str) or not data["expected_name"]:
            errors.append(f"{sidecar.name}: missing or empty 'expected_name'")
    assert not errors, "fixture sidecar issues:\n" + "\n".join(errors)
