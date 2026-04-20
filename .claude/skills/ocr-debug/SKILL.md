---
name: ocr-debug
description: Use when user wants to Context for debugging OCR misreads — coordinate spaces, preprocessing pipeline, cache state, and common failure patterns in inventory_vision.py
user-invocable: false
---

## Coordinate spaces in inventory_vision.py

Two spaces coexist. Mixing them is the #1 source of bugs:

- **Original space** — raw window crop dimensions
- **2x-upscaled space** — output of `preprocess_for_ocr()`, passed to Tesseract

Any bbox returned from Tesseract over a 2x image **must be halved** before use in original-space operations. `find_action_bbox_by_ocr` handles this division internally — callers receive original-space coords.

## Preprocessing pipeline order

Must be: `BGR → grayscale → upscale 2x → Otsu binarization → morphological ops → Tesseract`

Binarization must happen **before** morphological ops. Raw BGR must never go to Tesseract.

## Cache state

Module-level caches in `inventory_vision.py`:
- `_last_roi_hash` — skips re-OCR if region unchanged
- `_last_ocr_result` — cached result for the current ROI
- `_ITEM_NAMES` — loaded item name list for fuzzy matching

`reset_ocr_caches()` clears all three. It is called at the start of `scan_pages()`. If OCR results seem stale or items are missed after a new scan starts, the cache was not reset.

## Common misread patterns

| Symptom | Likely cause |
|---|---|
| Reads "unreadable" repeatedly | `_last_roi_hash` cache hit on a bad frame, or low contrast region |
| Same item name on every slot | Cache not reset between pages |
| Item name truncated | Title strip crop too narrow — check `TITLE_STRIP_*` constants |
| "Arc Alloy" false positives | Fuzzy threshold too low — rapidfuzz score below rejection threshold |
| Empty slots detected as items | `slot_bgr.size == 0` guard missing in `_find_first_empty_slot` |
| Item label shows "UNAVAILABLE" | Context-menu OCR fuzzy-matched the game's greyed-out "Unavailable" button as the item name — see `ocr-unavailable` skill |

## No-upscale fallback

`ocr_title_strip` automatically retries with `upscale=False` when the first attempt returns an empty item name. If a debug image from a 2x run looks wrong (interpolation artefacts around thin strokes), the fallback will try the raw-resolution crop. You can trigger the same path manually by calling `preprocess_for_ocr(roi, upscale=False)`.

## Debug images

OCR debug images land in `ocr_debug/` (timestamped PNGs). Key files:
- `*_infobox_detect_overlay.png` — infobox detection result
- `*_ctx_menu_processed.png` — context menu binarized crop
- `*_infobox_action_sell_processed.png` — sell/recycle button OCR region

When the title strip looks correct visually but OCR still misreads, the issue is almost always the binarization threshold or the upscale step being skipped.
