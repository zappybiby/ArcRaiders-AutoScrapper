---

name: lint-and-validate
description: Use when user wants to Run the Arc Raiders AutoScrapper validation stack after edits. Use for linting, typing, tests, workflow checks, and broader repo validation.

## Lint and validate

Choose the smallest validation set that matches the files you changed, then
expand if failures suggest a wider regression.

## Default validation sets

- Python source: `uv run ruff check src/ tests/ scripts/` -> `uv run basedpyright src/` -> `uv run pytest`
- Workflow files: `uv run prek run --files .github/workflows/<name>.yml`
- Docs or agent guidance: Verify paths, links, commands, and instruction hierarchy
- Broad repo sweep: `uv run prek run --all-files`

## Extra checks when needed

- OCR, scanner, interaction, or input changes also need

  `uv run autoscrapper scan --dry-run` against a live Arc Raiders window.

- Generated data or default-rule changes should come from

  `uv run python scripts/update_snapshot_and_defaults.py --dry-run` first, then
  the real update if the preview is correct.

- Quality passes can use `qlty check -a`, `qlty metrics -a`, and

  `qlty smells -a`.

## Quality loop

1. Make the smallest targeted edit.
2. Run the matching validation commands.
3. Fix issues caused by your change.
4. Re-run validation before marking the task done.

## Guardrails

- Do not finish with failing Ruff, BasedPyright, or pytest results caused by

  your change.

- If unrelated failures already exist, call them out explicitly in your final

  summary.

- Do not claim end-to-end OCR validation unless you used a live game

  window.
