Arc Raiders AutoScrapper uses Python 3.13, `uv`, Textual, Tesseract OCR,
OpenCV, screen capture, and optional desktop input automation. Start with
`/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/AGENTS.md`
for the full repo map, validation rules, and invariants.

## Start here

Use this file for startup guidance only. Keep detailed repo rules in
`AGENTS.md`, and keep path-specific instructions in
`.github/instructions/*.instructions.md`.

- Keep `CLAUDE.md` as a symlink to `AGENTS.md`.
- Prefer MCP tools and repo skills before broad shell or web searches.
- Keep edits minimal, targeted, and repo-specific.
- Do not hand-edit generated progress data or
  `src/autoscrapper/items/items_rules.default.json`.

## Core commands

Use these commands for the common setup and validation path in this repo.

- `python3 -m uv sync`
- `python3 -m uv run ruff check src/ tests/ scripts/`
- `python3 -m uv run basedpyright src/`
- `python3 -m uv run pytest`
- `python3 -m uv run prek run --files .github/workflows/<name>.yml`

## High-risk invariants

Treat these rules as non-negotiable when you edit OCR, scanner, interaction,
rules, or config code.

- `initialize_ocr()` must run on the main thread before scan threads start.
- Keep capture-space image coordinates separate from screen-space input
  coordinates.
- Keep OCR fuzzy matching aligned with rule lookup thresholds.
- Bump `CONFIG_VERSION` and add a migration when persisted config fields change.

## Preferred repo skills

Use these skills first when they match the task: `mcp-use`,
`language-optimization`, `codebase-index`, `workflow-development`,
`docs-writer`, `update-data`, `validate`, `lint-and-validate`, and
`copilot-init`.
