---
name: ocr-unavailable
description: Use when user wants to Triage guide for scans where item labels show "UNAVAILABLE" — root cause is context-menu OCR fuzzy-matching the game's greyed-out button label as the item name, not a missing action enum
user-invocable: false
---

## Symptom

Scan output shows item label `UNAVAILABLE` (or the scan skips items as `SKIP_UNLISTED` with item name "Unavailable").

## Root cause

`UNAVAILABLE` is **not** an action enum. It is the raw OCR text of the game's greyed-out "Unavailable" context-menu button being returned by `ocr_context_menu` as the item name.

**How it happens:** `ocr_context_menu` iterates context-menu lines top-to-bottom looking for a fuzzy match against known item names. When the item title region is absent or illegible (clipped crop, low contrast, upscale artefact), the loop falls through to a later line. The game's "Unavailable" button text can fuzzy-match a known item name via `fuzz.WRatio` partial matching at ≥75 score with ≥60% coverage, so it gets accepted as `item_name`.

## Required guards

`inventory_vision.py` `ocr_context_menu` must reject any match where `result.chosen_name.lower().startswith("unavailable")`. The `_ACTION_PREFIXES` list must also include `"unavailable"` as a line-level skip before fuzzy matching.

If this symptom recurs, both guards may have been removed or bypassed — check both.

## Triage checklist

1. **Check the guard** — search `inventory_vision.py` for `startswith("unavailable")`; if missing, re-add the post-match filter after the coverage check.

2. **Check the context-menu crop** — open `ocr_debug/*_ctx_menu_processed.png`. If the item title row is blank or garbled, the title region is being cropped incorrectly or the game window moved.

3. **Check preprocessing order** — must be BGR → grayscale → upscale 2x → Otsu. If upscale happens before grayscale, interpolation degrades character edges and the title line may become unreadable. See `preprocess_for_ocr` in `inventory_vision.py`.

4. **No-upscale fallback** — `ocr_title_strip` retries with `upscale=False` automatically if the first pass returns empty. If both passes fail, the item title line is genuinely unreadable from the crop — the crop constants (`_TITLE_STRIP_*`) may need recalibration.

5. **`_ACTION_PREFIXES` filter** — `_ACTION_PREFIXES` in `ocr_context_menu` includes `"unavailable"` as a line-level prefix skip. This filter runs on raw line text *before* fuzzy matching; the post-match `startswith` guard runs *after*. Both must be present.

## Related skills

- `ocr-debug` — coordinate spaces, preprocessing order, cache state
- `scan-failed` — when OCR is correct but the sell/recycle decision is wrong
