---

name: diagnose-scan
description: Run a dry-run scan, capture output, then route to the correct reviewer agent based on failure type (OCR errors → ocr-reviewer, timing/detection → scan-validator, rules → rules-reviewer).

## Diagnose Scan Failures

Run a dry-run scan and automatically route the results to the right specialist.

### Step 1 - Run dry-run scan

```bash
uv run autoscrapper scan --dry-run 2>&1 | tee /tmp/scan-diag.txt
```

Debug images land in `ocr_debug/` with timestamps:

- `*_infobox_detect_overlay.png`: Infobox detection - green = detected, red = missed
- `*_ctx_menu_processed.png`: Context menu crop after binarization - should show clear text
- `*_infobox_action_sell_processed.png`: Sell/recycle button OCR region - check text is legible

Common failure indicators in the images:

- Infobox not detected → wrong crop region or window resize
- Garbled text → binarization threshold or upscale issue
- Item name "unreadable" → check fuzzy match score in logs (low score = preprocessing issue, not a rules issue)
- Action button wrong text → binarization inverted (black-on-white vs white-on-black)

### Step 2 - Classify the failure

Read `/tmp/scan-diag.txt` and determine failure type:

- `tesseract`, `OCR`, `image_to_string`, garbled item names: `ocr-reviewer` agent
- `page_state`, `detect`, timeout, `infobox not found`: `scan-validator` agent
- `SKIP_UNLISTED`, wrong action, rule not matched: `rules-reviewer` agent
- `config`, `CONFIG_VERSION`, deserialization error: `config-reviewer` agent

### Step 3 - Dispatch to specialist

Use the `Agent` tool with the appropriate subagent type:

- **OCR failures** → `subagent_type: "ocr-reviewer"` - pass the raw log + relevant `ocr_debug/` image timestamps
- **Scan/detection failures** → `subagent_type: "scan-validator"` - pass the log + page state transitions
- **Rules failures** → `subagent_type: "rules-reviewer"` - pass item names that got wrong actions
- **Config failures** → `subagent_type: "config-reviewer"` - pass the config diff

### Step 4 - After fix

Re-run the dry-run to confirm the failure is resolved:

uv run autoscrapper scan --dry-run 2>&1 | tail -20

If `ocr_debug/` grew during diagnosis, run `/clean-debug 1` to prune images from this session.
