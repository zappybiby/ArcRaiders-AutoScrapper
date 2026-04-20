---
name: calibrate-vision
description: Workflow for recalibrating the context-menu crop constants in inventory_vision.py. Use when the context menu is being cropped at the wrong position, missed entirely, or when the game UI layout changes. Constants are normalized to 1920x1080.
disable-model-invocation: true
---

# Calibrate Vision Constants

The context-menu crop region in `src/autoscrapper/ocr/inventory_vision.py` is defined by four normalized constants (calibrated at 1920×1080):

```python

# Lines ~554-558
_CONTEXT_MENU_X_OFFSET_NORM = 35 / 1920 # pixels right of cell centre
_CONTEXT_MENU_Y_OFFSET_NORM = -20 / 1080 # pixels above cell centre (negative = up)
_CONTEXT_MENU_WIDTH_NORM = 420 / 1920 # crop width
_CONTEXT_MENU_HEIGHT_NORM = 450 / 1080 # crop height
```

These are multiplied by `img_w` / `img_h` at runtime (lines ~581–584), so they work at any resolution. When the game UI shifts or a different overlay position is used, re-derive the raw pixel values and divide by 1920/1080.

## When to recalibrate

- Context-menu OCR returns blank or wrong text
- Sell/Recycle/Keep options are not found despite the menu being visible
- The game client changed its UI layout or DPI scaling
- `ocr_debug/` images show the context menu partially outside the crop

## Steps

### 1. Capture a reference screenshot

Run a dry-run scan to capture `ocr_debug/` images:

```bash
uv run autoscrapper scan --dry-run

Open an `ocr_debug/context_menu_*.png` (or `infobox_*.png`) to see what the current crop is capturing.

### 2. Measure the correct crop in the raw capture
Open the full window capture image (before any crop) in an image viewer that shows pixel coordinates. Identify:

- `x_offset`: pixels from the **centre of the inventory cell** to the **left edge of the context menu**
- `y_offset`: pixels from the cell centre to the **top edge** of the menu (negative if menu is above centre)
- `height`: total height of the context menu

# Replace 1920/1080 with your capture resolution if different
x_offset_norm = measured_x_offset_px / 1920
y_offset_norm = measured_y_offset_px / 1080 # keep sign
width_norm = measured_width_px / 1920
height_norm = measured_height_px / 1080

### 4. Update the constants
Edit `src/autoscrapper/ocr/inventory_vision.py` lines ~554–558:

_CONTEXT_MENU_X_OFFSET_NORM = <new_x> / 1920
_CONTEXT_MENU_Y_OFFSET_NORM = <new_y> / 1080
_CONTEXT_MENU_WIDTH_NORM = <new_w> / 1920
_CONTEXT_MENU_HEIGHT_NORM = <new_h> / 1080

### 5. Validate
Check that `ocr_debug/context_menu_*.png` now shows the full menu clearly. Verify Sell/Recycle/Keep are detected correctly in the scan output.

uv run pytest tests/autoscrapper/ocr/ -v

## Other normalized constants
`SELL_CONFIRM_RECT_NORM`, Location=line ~37, Purpose=Sell confirmation button
`RECYCLE_CONFIRM_RECT_NORM`, Location=line ~38, Purpose=Recycle confirmation button
`INVENTORY_COUNT_RECT_NORM`, Location=line ~42, Purpose=Item count text region
`TITLE_HEIGHT_REL`, Location=line ~34, Purpose=Infobox title crop height

These follow the same normalization pattern - raw pixels at 1920×1080 divided by 1920 or 1080.
```
