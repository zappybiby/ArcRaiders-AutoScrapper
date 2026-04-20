---
name: ci-promote
description: Use when user wants to Run full validation, push branch, and open a PR with appropriate context notes
disable-model-invocation: true
---

Pre-push checklist — run all steps before opening PR:

```bash
# 1. Tests
uv run pytest

# 2. Lint
uv run ruff check src/ tests/

# 3. Types
uv run basedpyright src/
```

If OCR or scanner files changed (`inventory_vision.py`, `scan_loop.py`, `tesseract.py`):
- Note **"corpus replay required"** in the PR body
- Flag **T001** if any `threshold`/`score_cutoff` value changed

Push and open PR:

```bash
git push -u origin HEAD
gh pr create --title "<title>" --body "<body>"
```

PR body checklist:
- [ ] Tests passing
- [ ] Ruff clean
- [ ] Basedpyright clean
- [ ] OCR changes: corpus replay run (or note if skipped)
- [ ] Config changes: `CONFIG_VERSION` bumped if fields changed
- [ ] Generated data changes: regenerated via script, not hand-edited
