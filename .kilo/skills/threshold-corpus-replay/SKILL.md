---
name: threshold-corpus-replay
description: Use when user wants to Replay OCR corpus against a candidate threshold value to validate before shipping a threshold change. Use specifically for changes to fuzzy match threshold or score_cutoff. For general OCR code changes, use /ocr-corpus-replay instead.
disable-model-invocation: true
---

# Threshold Corpus Replay

Use this skill before shipping any change to the fuzzy match threshold or OCR confidence cutoff in `core/item_actions.py` or `ocr/inventory_vision.py`.

> **Scope:** This skill is for threshold tuning only. For changes to OCR preprocessing or detection code, use `/ocr-corpus-replay` instead.

## What is the corpus?

Timestamped PNG snapshots saved to `ocr_debug/` during real scan sessions. Each image is a cropped infobox captured at scan time. The corpus accumulates across sessions - do not clear it before a replay.

If `ocr_debug/` is empty, run a dry-run scan first to populate it:

```bash
uv run autoscrapper scan --dry-run
```

## How to replay

1. Note the current threshold value in `core/item_actions.py` (`FUZZY_THRESHOLD` or equivalent constant).
2. Set the candidate value in a local branch.
3. Run the replay script:

uv run python scripts/replay_corpus.py --threshold <candidate_value>

If `replay_corpus.py` does not exist yet, use the manual approach:

uv run pytest tests/autoscrapper/core/test_item_actions.py tests/autoscrapper/ocr/ -v

4. Compare match rates before and after. A threshold change is safe to ship when:

- No previously-matched item names drop below the threshold (zero regressions)
- At least one previously-failing item now matches (measurable improvement), OR the change is a deliberate tightening with known false-positive reduction

## Pass/fail criteria

- All prior matches retained, improvement observed: Ship
- All prior matches retained, no change: Reconsider - threshold change has no effect
- Any prior match lost: Do NOT ship - regression

## Related

- `TODO T001` in codebase - tracks threshold tuning work
- Hook in `.claude/settings.json` warns on threshold edits and references this skill
- Both `core/item_actions.py` and `ocr/inventory_vision.py` share the same threshold constant - change it in one place only
- `/ocr-corpus-replay` - for validating OCR code changes (not threshold changes)
- `/threshold-change` - full safe workflow for threshold changes including baseline capture
