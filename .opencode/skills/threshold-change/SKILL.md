---

name: threshold-change
description: Safe workflow for changing fuzzy-match threshold or OCR confidence cutoff values. Use whenever editing threshold/score_cutoff in core/item_actions.py or ocr/inventory_vision.py. Corpus replay required before shipping - see T001.
disable-model-invocation: true

# Threshold Change

Changing the fuzzy-match threshold or OCR confidence cutoff affects every item match decision. A wrong value causes false positives (wrong action taken) or missed matches (items skipped). **Corpus replay is required before shipping.**

This is TODO T001 in the codebase. The hook in `settings.json` fires a warning whenever you edit a threshold constant.

## Where the thresholds live

```bash
grep -rn 'FUZZY_THRESHOLD\|score_cutoff\|threshold' src/autoscrapper/core/item_actions.py
grep -rn 'threshold\|THRESHOLD' src/autoscrapper/ocr/inventory_vision.py
```

Both files share the same constant - change it in **one place only**.

## Steps

### 1. Note the current value

grep -n 'FUZZY_THRESHOLD\|score_cutoff' src/autoscrapper/core/item_actions.py

Record: `before = <current_value>`

### 2. Populate the corpus if empty

ls ocr_debug/

If empty, run a dry-run scan to populate it:

uv run autoscrapper scan --dry-run

The corpus must not be cleared between now and the replay. See the `corpus-replay` skill.

### 3. Run corpus replay at the CURRENT value (baseline)

uv run pytest tests/autoscrapper/core/test_item_actions.py tests/autoscrapper/ocr/ -v 2>&1 | tee /tmp/threshold_before.txt

Record pass/fail counts from the summary line.

### 4. Set the candidate value

Edit the threshold constant in `src/autoscrapper/core/item_actions.py`.

### 5. Run corpus replay at the NEW value

uv run pytest tests/autoscrapper/core/test_item_actions.py tests/autoscrapper/ocr/ -v 2>&1 | tee /tmp/threshold_after.txt

### 6. Compare

diff /tmp/threshold_before.txt /tmp/threshold_after.txt

Apply the `corpus-replay` skill pass/fail criteria:

- All prior matches retained + improvement observed: Ship
- All prior matches retained, no change: Reconsider - no measurable effect
- Any prior match lost: **Do NOT ship - regression**

### 7. If safe to ship - run full validation

uv run ruff check src/ tests/
uv run pytest

## Related

- `threshold-corpus-replay` skill - detailed replay procedure
- `ocr-reviewer` agent - review the surrounding code change
- T001 in `src/autoscrapper/core/item_actions.py`
