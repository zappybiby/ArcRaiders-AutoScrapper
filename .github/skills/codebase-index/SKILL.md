---

name: codebase-index
description: Index and search the Arc Raiders AutoScrapper codebase efficiently. Use when you need the repo map, hotspots, or the right module for a change.

## Codebase index

Use this skill to locate the right module before editing. Start with the
canonical guidance in `AGENTS.md`, then drill into the relevant workflow.

## Read order

1. `AGENTS.md`
2. `.github/copilot-instructions.md`
3. `pyproject.toml`
4. The module family that matches the task

## High-value paths

- `src/autoscrapper/tui/`: Textual screens and scan entry points
- `src/autoscrapper/scanner/`: Scan loop, page traversal, reporting, action execution
- `src/autoscrapper/interaction/`: Screen capture, grid detection, platform input
- `src/autoscrapper/ocr/`: Tesseract setup, preprocessing, infobox and menu OCR
- `src/autoscrapper/core/item_actions.py`: KEEP / SELL / RECYCLE decision logic
- `src/autoscrapper/items/rules_store.py`: Custom rule persistence and default-rule overlay
- `src/autoscrapper/config.py`: Persisted config dataclasses and config versioning
- `src/autoscrapper/progress/`: Generated snapshot data and default-rule inputs
- `scripts/update_snapshot_and_defaults.py`: Generator for progress data and bundled defaults
- `tests/`: Pytest coverage for OCR, scanner, rules, and scripts

## Hotspots and guardrails

- `src/autoscrapper/ocr/`, `src/autoscrapper/interaction/`, and

  `src/autoscrapper/scanner/` are tightly coupled.

- `src/autoscrapper/ocr/inventory_vision.py` is the most calibration-sensitive

  file in the repo.

- Preserve custom-over-default rule precedence.
- Do not hand-edit `src/autoscrapper/progress/data/*` or

  `src/autoscrapper/items/items_rules.default.json`; use the `update-data`
  skill or the update script.

- `initialize_ocr()` must run on the main thread before scan threads start.
- Keep capture-space image coordinates separate from screen-space input

  coordinates.

- Keep OCR fuzzy matching aligned with rule lookup thresholds.

## Useful commands

```bash
uv run ruff check src/ tests/ scripts/
uv run basedpyright src/
uv run pytest
uv run autoscrapper scan --dry-run
uv run python scripts/update_snapshot_and_defaults.py --dry-run
```

## Search hints

rg "initialize_ocr|CONFIG_VERSION|score_cutoff|threshold" src/ tests/
rg "KEEP|SELL|RECYCLE|rules_store|item_actions" src/ tests/
rg "update_snapshot_and_defaults|metadata.json|items_rules.default.json" src/ tests/ scripts/
