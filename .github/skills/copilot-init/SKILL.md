---

name: copilot-init
description: Refresh Copilot bootstrap guidance for this Python 3.13 / uv OCR repo. Use when asked to initialize Copilot guidance, update `copilot-setup-steps`, or improve repo-specific agent guidance.
allowed-tools: 'Read, Write, Edit, Glob, Grep, Bash'

# Copilot init

Refresh the repo's Copilot bootstrap assets using the repository itself as the
source of truth.

## Repo baseline

- Canonical long-form guidance lives in `AGENTS.md`; keep `CLAUDE.md` as a

  symlink to it.

- Keep `.github/copilot-instructions.md` short and startup-focused.
- The repo is Python 3.13 with `uv`, Textual, Tesseract OCR, OpenCV, and screen

  automation.

- Core validation commands are `uv run ruff check src/ tests/ scripts/`,

  `uv run basedpyright src/`, `uv run pytest`, and
  `uv run prek run --files .github/workflows/<name>.yml`.

## What to update

- `.github/workflows/copilot-setup-steps.yml`, `.github/instructions/*.instructions.md`, `.github/skills/*/SKILL.md`
- Focused workflows only when the repo is missing real coverage for its actual

  stack

## Workflow

1. Audit the existing guidance, skills, workflows, and commands before editing.
2. Keep startup bootstrap in `.github/copilot-instructions.md` and repo-wide

   rules in `AGENTS.md`.

3. Prefer small, repo-specific instruction and skill files over generic

   templates.

4. Keep `copilot-setup-steps` aligned with the real setup path:

   `actions/checkout@v6`, `astral-sh/setup-uv@v7`, OCR system packages, and
   `uv sync --frozen`.

5. Reuse existing workflows when they already cover Ruff, BasedPyright, pytest,

   Biome, or data refresh.

6. Call out generated files and calibration-sensitive OCR invariants instead of

   duplicating large rule blocks across many files.

7. Validate changed workflows and verify every referenced command and path.

## Guardrails

- Do not invent tools, packages, paths, or workflows.
- Do not hand-edit `src/autoscrapper/progress/data/*` or

  `src/autoscrapper/items/items_rules.default.json`.

- Do not broaden setup or CI to optional extras unless the workflow truly needs

  them.

- Prefer updating strong existing files over creating duplicates.
