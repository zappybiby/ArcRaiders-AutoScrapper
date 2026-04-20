# CI Promote

Run full validation, push branch, and open a PR.

**Pre-push checklist:**
```bash
# 1. Tests
uv run pytest

# 2. Lint
uv run ruff check src/ tests/

# 3. Types
uv run basedpyright src/
```

**If OCR/scanner files changed** (`inventory_vision.py`, `scan_loop.py`, `tesseract.py`):
- Note **"corpus replay required"** in PR body
- Flag **T001** if threshold/score_cutoff changed

**Push and open PR:**
```bash
git push -u origin HEAD
gh pr create --title "<title>" --body "<body>"
```

**PR body checklist:**
- [ ] Tests passing
- [ ] Ruff clean
- [ ] Basedpyright clean
- [ ] OCR changes: corpus replay run (or note if skipped)
- [ ] Config changes: `CONFIG_VERSION` bumped if fields changed
- [ ] Generated data changes: regenerated via script, not hand-edited

**Related:** Skills: `ci-promote`, `upstream-sync` | Agent: `security-reviewer`
