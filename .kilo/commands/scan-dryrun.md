# Scan Dry Run

Run OCR/scanner validation without triggering clicks.

**Command:** `uv run autoscrapper scan --dry-run`

**Validation:** Inspect `ocr_debug/` for:

- `*_infobox_detect_overlay.png` - Infobox detection
- `*_ctx_menu_processed.png` - Context menu crop
- `*_infobox_action_sell_processed.png` - Sell/recycle button OCR
