---

applyTo: "**"

## Review focus

- Start with `AGENTS.md` plus any path-specific instruction file.
- Prioritize correctness and safety in `src/autoscrapper/ocr/`,

  `src/autoscrapper/interaction/`, `src/autoscrapper/scanner/`,
  `src/autoscrapper/core/item_actions.py`,
  `src/autoscrapper/items/rules_store.py`, and `src/autoscrapper/config.py`.

- Block on hand-edited generated data, missing config migrations, OCR threading

  regressions, capture-vs-screen coordinate mixups, workflow over-permissioning,
  and unsupported validation claims.

## Validation expectations

- Python changes: `uv run ruff check src/ tests/ scripts/`,

  `uv run basedpyright src/`, `uv run pytest`

- Workflow changes: `uv run prek run --files .github/workflows/<name>.yml`
- OCR, scanner, interaction, or input changes: only claim

  `uv run autoscrapper scan --dry-run` validation if a live game window was used

## Comment style

- Use `MUST`, `SHOULD`, `CONSIDER`, and `QUESTION`.
- Cite the exact file or command affected and explain the impact briefly.
