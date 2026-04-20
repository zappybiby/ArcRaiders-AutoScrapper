# Add OCR Fixture

Lock in a correct OCR result as a regression test.

**Prerequisites:** Run a dry-run to populate `ocr_debug/`:
```bash
uv run autoscrapper scan --dry-run
```

**Add the fixture:**
```bash
uv run python scripts/capture_ocr_fixture.py <path_to_image> "<Expected Item Name>"
```

**Example:**
```bash
uv run python scripts/capture_ocr_fixture.py ocr_debug/infobox_3.png "Rusty Gear"
```

**Output:**
- `tests/fixtures/ocr/<slug>.png` - source image
- `tests/fixtures/ocr/<slug>.json` - sidecar with expected_name, source, captured_at

**Verify:**
```bash
uv run pytest tests/autoscrapper/ocr/test_ocr_fixtures.py -v
```

**Run full OCR suite:**
```bash
uv run pytest tests/autoscrapper/ocr/ -v
```

**Notes:**
- Fixture slugs are derived from item name: `"Arc Alloy"` → `arc_alloy.png`
- `ocr_debug/` is disposable; fixtures in `tests/fixtures/ocr/` are committed

**Related:** Skill: `add-fixture` | Agent: `ocr-reviewer`
