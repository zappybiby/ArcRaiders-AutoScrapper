---
name: validate
description: Run the correct validation checks for changed files in this repository (Python, workflows, guidance, and generated data).
allowed-tools: 'Read, Bash, Grep, Glob'
---

# Validate

Run the narrowest checks that cover the files you changed.

## Identify the changed area

- `src/**/*.py`, `tests/**/*.py`, `scripts/**/*.py`, or `pyproject.toml`
- OCR, scanner, interaction, or input code under `src/autoscrapper/ocr/`,
  `src/autoscrapper/scanner/`, or `src/autoscrapper/interaction/`
- Generated data or bundled default rules
- `.github/` workflows, instructions, or skills
- Repo guidance such as `AGENTS.md`, `CLAUDE.md`, or
  `.github/copilot-instructions.md`

## Checks

**Python source**

```bash
uv sync
uv run ruff check src/ tests/ scripts/
uv run basedpyright src/
uv run pytest
```

**OCR, scanner, interaction, or input changes**

Run the Python source checks above, then also run this only when a live Arc
Raiders window is available:

```bash
uv run autoscrapper scan --dry-run
```

**Generated data or bundled default rules**

Use the updater rather than hand-editing generated files:

```bash
uv sync
uv run python scripts/update_snapshot_and_defaults.py --dry-run
```

**Workflow files**

```bash
uv sync
uv run prek run --files .github/workflows/<name>.yml
```

**Instructions, skills, or repo guidance**

- Verify every referenced path, command, and workflow still exists.
- Re-run referenced repo commands when practical.
- Keep `AGENTS.md` as the canonical long-form guide and keep
  `.github/copilot-instructions.md` short.

## Guardrails

- Never skip a required check just to get a green result.
- Report pre-existing failures that are unrelated to your change.
- Do not claim live OCR validation unless you actually used a live game window.
