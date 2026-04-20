# Change Threshold

Safely adjust fuzzy-match threshold or OCR confidence cutoff.

**Warning:** Requires corpus replay before shipping. See T001 in `item_actions.py`.

**Where thresholds live:**
```bash
grep -rn 'FUZZY_THRESHOLD|score_cutoff' src/autoscrapper/core/item_actions.py
grep -rn 'threshold|THRESHOLD' src/autoscrapper/ocr/inventory_vision.py
```

Both files share the same constant - change in **one place only**.

**Steps:**
1. **Record current value** - `before = <value>`
2. **Populate corpus if empty:** `uv run autoscrapper scan --dry-run`
3. **Run baseline tests:**
   ```bash
   uv run pytest tests/autoscrapper/core/test_item_actions.py tests/autoscrapper/ocr/ -v 2>&1 | tee /tmp/threshold_before.txt
   ```
4. **Set candidate value** in `src/autoscrapper/core/item_actions.py`
5. **Run new-value tests:**
   ```bash
   uv run pytest tests/autoscrapper/core/test_item_actions.py tests/autoscrapper/ocr/ -v 2>&1 | tee /tmp/threshold_after.txt
   ```
6. **Compare:** `diff /tmp/threshold_before.txt /tmp/threshold_after.txt`

**Pass criteria:**
- All prior matches retained + improvement → Ship
- All prior matches retained, no change → Reconsider
- Any prior match lost → **Do NOT ship**

**After shipping:**
```bash
uv run ruff check src/ tests/
uv run pytest
```

**Related:** Skills: `threshold-change`, `threshold-corpus-replay` | Agent: `ocr-reviewer`
