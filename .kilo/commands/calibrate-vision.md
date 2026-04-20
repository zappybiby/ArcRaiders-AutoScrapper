# Calibrate Vision

Recalibrate context-menu crop constants.

**When to recalibrate:**
- Context-menu OCR returns blank/wrong text
- Sell/Recycle/Keep options not found
- Game UI layout changed
- `ocr_debug/` shows partial menu crops

**Steps:**
1. Capture reference: `uv run autoscrapper scan --dry-run`
2. Open `ocr_debug/context_menu_*.png` to measure correct crop
3. Measure from cell centre to menu edges (in pixels at 1920x1080)
4. Update constants in `src/autoscrapper/ocr/inventory_vision.py` (~lines 554-558)

**Constants to adjust:**
- `_CONTEXT_MENU_X_OFFSET_NORM`
- `_CONTEXT_MENU_Y_OFFSET_NORM`
- `_CONTEXT_MENU_WIDTH_NORM`
- `_CONTEXT_MENU_HEIGHT_NORM`

**Validate:** `uv run pytest tests/autoscrapper/ocr/ -v`

**Related:** Skill: `calibrate-vision` | Agent: `ocr-reviewer`
