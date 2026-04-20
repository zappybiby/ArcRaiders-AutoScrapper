---
name: validate
description: Run the correct validation checks for changed files in this repository (Bun frontend checks, uv Python checks, and workflow or guidance verification).
allowed-tools: 'Read, Bash, Grep, Glob'
---

# Validate

Run the narrowest checks that cover the files you have changed.

## Triggers

Use this skill when asked to validate, lint, type-check, or test changes before committing.

## Steps

1. Identify which repo areas changed:
   - `apps/web`
   - `apps/api`
   - `packages/config`
   - `packages/llm-core`
   - `packages/shared/python`
   - `packages/code-index`
   - `.github/` workflows, instructions, or skills

2. Run only the checks relevant to changed files:

   **Frontend (`apps/web/**/*.{js,jsx,ts,tsx}`)**

   ```bash
   cd apps/web
   bun install
   bun run lint
   bun run typecheck
   bun run build
   ```

   **API (`apps/api/**/*.py`)**

   ```bash
   cd apps/api
   export PYTHONPATH=src:../../packages/config/src
   uv sync --all-extras
   uv run ruff format --check
   uv run ruff check
   uv run pyrefly check
   uv run pytest
   ```

   **Shared Python packages (`packages/config`, `packages/shared/python`, `packages/code-index`, `packages/llm-core`)**

   ```bash
   cd <package>
   uv sync
   uv run ruff format --check src/
   uv run ruff check src/
   ```

   **Workflow, instruction, or skill changes under `.github/`**

   ```bash
   Verify every referenced path and command exists.
   Re-run the repo commands referenced by the changed guidance when practical.
   ```

3. Fix reported issues in the changed files only. Do not touch unrelated files.

4. Re-run the affected check to confirm it passes before reporting success.

## Invariants

- Never remove or skip a check to make it pass.
- Do not modify test files to suppress failures unless the test itself is wrong.
- Report any pre-existing failures that are unrelated to your changes rather than silently fixing them.
