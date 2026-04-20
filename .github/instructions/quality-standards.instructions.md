---
applyTo: "**"
---

## Repo quality standards

- Keep edits minimal, targeted, and repo-specific.
- Use `AGENTS.md` as the canonical long-form guide; avoid duplicating large rule
  blocks across other files.
- Do not hand-edit `src/autoscrapper/progress/data/*` or
  `src/autoscrapper/items/items_rules.default.json`.
- When persisted config fields change, bump `CONFIG_VERSION` and add a
  migration.
- Preserve OCR invariants: main-thread `initialize_ocr()`, separate Tesseract
  API locks, capture-space vs screen-space separation, and shared fuzzy
  thresholds.

## Validation

- Python changes: `uv sync`, `uv run ruff check src/ tests/ scripts/`,
  `uv run basedpyright src/`, `uv run pytest`
- Workflow changes: `uv run prek run --files .github/workflows/<name>.yml`
- Docs, guidance, and skills: verify referenced paths, commands, and links
- Live OCR validation is only complete when a real Arc Raiders window was used

## Review heuristics

- Prefer correctness, maintainability, and security over speculative rewrites.
- Call out pre-existing failures instead of silently fixing unrelated areas.
- Do not broaden dependencies, extras, or workflows without a repo-specific
  need.
