# OCR Corpus Replay

Validate OCR changes against recorded failure corpus.

**Command:** `uv run python scripts/replay_ocr_failure_corpus.py`

**Options:**
- `--check-only` - Don't fail on first error
- `--verbose` - Show detailed diff for failures

**When to use:**
- After modifying `src/autoscrapper/ocr/inventory_vision.py`
- After changing threshold/score_cutoff values
- Before shipping OCR-related changes

**Warning:** Never ship OCR changes without corpus replay validation.

**Related:** Skill: `ocr-corpus-replay` | Agent: `ocr-reviewer`
