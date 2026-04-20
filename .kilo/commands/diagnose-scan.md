# Diagnose Scan

Run a dry-run scan and route failures to the correct specialist.

**Command:** `uv run autoscrapper scan --dry-run 2>&1 | tee /tmp/scan-diag.txt`

**Debug images land in `ocr_debug/`:**
- `*_infobox_detect_overlay.png` - green = detected, red = missed
- `*_ctx_menu_processed.png` - context menu after binarization
- `*_infobox_action_sell_processed.png` - sell/recycle button OCR region

**Classify failure from logs:**
- `tesseract`, `OCR`, garbled text → **ocr-reviewer**
- `page_state`, `detect`, timeout, infobox not found → **scan-validator**
- `SKIP_UNLISTED`, wrong action, rule not matched → **rules-reviewer**
- `config`, `CONFIG_VERSION` error → **config-reviewer**

**After fix:** Re-run dry-run to confirm.

**Cleanup:** `python3 -c "..."` (see `/clean-debug 1`) to remove session debug images.

**Related:** Skills: `diagnose-scan`, `scan-report`, `triage-failures` | Agents: `ocr-reviewer`, `scan-validator`, `rules-reviewer`
