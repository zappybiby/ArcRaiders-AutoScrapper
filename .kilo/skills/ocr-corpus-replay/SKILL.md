---
name: ocr-corpus-replay
description: Use when user wants to Validate OCR changes against failure corpus before shipping
disable-model-invocation: true
context: fork
---

# OCR Corpus Replay Skill

Replay recorded OCR failures to validate vision/preprocessing changes don't cause regressions.

## When to Use

- After modifying `src/autoscrapper/ocr/inventory_vision.py`
- After changing threshold/score_cutoff values in fuzzy matching
- Before shipping OCR-related changes
- When investigating OCR accuracy issues

## Usage

```bash

# Validate with default settings (fail fast on first error)
/ocr-corpus-replay

# Check corpus without failing on first error
/ocr-corpus-replay --check-only

# Show detailed diff for failures
/ocr-corpus-replay --verbose
```

## What It Does

1. Loads recorded OCR failure cases from the corpus
2. Re-extracts text/boxes using current implementation
3. Compares output against baseline
4. Reports: match count, deviation count, coordinate shifts, threshold impact
5. Returns exit code 0 (pass) or 1 (fail) for CI integration

## Behind the Scenes

Runs: `uv run python scripts/replay_ocr_failure_corpus.py [args]`

Validates:

- Text extraction accuracy (fuzzy match threshold T001)
- Bounding box coordinate stability
- Upscale artifact handling
- Preprocessing pipeline consistency

## Critical Note

**Never ship OCR changes without corpus replay validation.** The corpus captures real-world cases that point detection or preprocessing changes can subtly break.

*Invoke with `/ocr-corpus-replay` after OCR edits.*
