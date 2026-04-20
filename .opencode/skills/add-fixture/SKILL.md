---

name: add-fixture
description: Add a new OCR regression fixture from an ocr_debug image. Use when a scan misidentified an item and you want to lock in the correct result as a test case.
disable-model-invocation: true

# Add OCR Fixture

When OCR misidentifies an item, capture a regression fixture so the failure can never silently recur.

## Prerequisites

The `ocr_debug/` directory must contain the problem image. Run a dry-run scan if it is empty:

```bash
uv run autoscrapper scan --dry-run
```

## Add the fixture

uv run python scripts/capture_ocr_fixture.py <path_to_image> "<Expected Item Name>"

**Example:**

uv run python scripts/capture_ocr_fixture.py ocr_debug/infobox_3.png "Rusty Gear"

**Output:**

tests/fixtures/ocr/rusty_gear.png ← copy of the source image
tests/fixtures/ocr/rusty_gear.json ← sidecar: expected_name, source, captured_at

If the fixture already exists, the script prompts before overwriting.

## Verify the fixture passes

uv run pytest tests/autoscrapper/ocr/test_ocr_fixtures.py -v

If it fails, the OCR is still broken - this is now a tracked regression. Fix the OCR logic, then rerun until the fixture passes.

## Run the full OCR suite

uv run pytest tests/autoscrapper/ocr/ -v

All existing fixtures must still pass after adding the new one.

## Notes

- Fixture slugs are derived from the item name: `"Arc Alloy"` → `arc_alloy.png`
- Do not hand-edit sidecar JSON - recreate via the script if corrections are needed
- `ocr_debug/` is disposable and is not committed; fixtures in `tests/fixtures/ocr/` are committed
