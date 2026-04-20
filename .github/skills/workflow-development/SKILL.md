---
name: workflow-development
description: Create, debug, and optimize GitHub Actions workflows for this Python 3.13 / uv repository.
allowed-tools: "Bash, Read, Write, Edit, Glob, Grep"
---

# Workflow Development

Create or update GitHub Actions workflows for this Python 3.13 / uv repo.

## Repo defaults

- Start with `AGENTS.md` and `.github/instructions/cicd-standards.instructions.md`.
- Pin actions to versions already used here: `actions/checkout@v6`,
  `astral-sh/setup-uv@v7`, and `actions/upload-artifact@v7`.
- Set `persist-credentials: false` on checkout unless the job must push.
- Prefer `uv sync --frozen`; add extras only when a workflow truly needs them.
- OCR and Tesseract jobs usually need `build-essential`, `pkg-config`,
  `tesseract-ocr`, `libtesseract-dev`, and `libleptonica-dev`.
- Add Linux input or evdev packages only when the workflow actually exercises
  Linux input automation.

## Existing workflow purposes

- `ruff.yml`: Ruff, BasedPyright, and pytest validation.
- `biome.yml`: repo formatting and lint guard.
- `daily-data-update.yml`: scheduled snapshot and default-rule refresh.
- `copilot-setup-steps.yml`: agent bootstrap environment.

## Workflow process

1. Match the trigger set to the workflow's real purpose.
2. Keep permissions minimal.
3. Use the repository's real commands and lockfiles.
4. Reuse existing jobs when coverage already exists.
5. Validate workflow edits with `uv run prek run --files .github/workflows/<name>.yml`.

## Guardrails

- Do not claim a workflow is safe unless referenced commands, paths, and
  secrets exist.
- Avoid `--all-extras` in setup-only workflows.
- Do not add workflows for languages or tools this repo does not use.
