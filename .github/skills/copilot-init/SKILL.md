---
name: copilot-init
description: Bootstrap Copilot guidance for any repository by creating or updating `.github/workflows/copilot-setup-steps.yml`, focused lint/check/test workflows, `.github/instructions/*.instructions.md`, and `.github/skills/*/SKILL.md`. Use when asked to initialize Copilot guidance, scaffold repo instructions or skills, create or update `copilot-setup-steps`, or add Copilot-facing validation workflows.
allowed-tools: 'Read, Write, Edit, Glob, Grep, Bash'
---

# Copilot init

Create or refresh Copilot bootstrap assets for the current repository. Derive all guidance from the repository itself and from files already present in the repo. Do not paste generic templates without adapting them.

## Goal

Produce a minimal, high-signal set of bootstrap and validation assets:

- `.github/workflows/copilot-setup-steps.yml`
- focused lint/check/test workflows when the repository does not already have the right coverage
- `.github/instructions/*.instructions.md`
- `.github/skills/*/SKILL.md`

Keep startup guidance short, keep detailed repo-wide guidance in a single canonical place when the repository has one, and avoid duplicating large rule blocks across files.

## Workflow

1. Audit the repository.
   - Identify languages, toolchains, package managers, entry points, and major workflows.
   - Collect setup, lint, test, type-check, build, and release commands.
   - Inspect existing workflows, instructions, skills, and agent guidance before adding files.
   - Note required system packages, services, or runtime prerequisites.
   - Only plan linting, checking, and testing that is relevant to the current repository. Do not add workflows for languages or tools the project does not use.
2. Design the guidance split.
   - `.github/copilot-instructions.md`: short startup bootstrap only.
   - Repo-wide guide, if present: canonical long-form guidance.
   - `.github/instructions/`: path- or topic-specific rules.
   - `.github/skills/`: reusable task workflows.
3. Create or update `.github/workflows/copilot-setup-steps.yml`.
   - Keep triggers minimal: `workflow_dispatch` plus `push` and
     `pull_request` scoped to the workflow file.
   - Set minimal `permissions:`.
   - Use pinned action versions.
   - Install only the repository's real system dependencies, toolchain, and project dependencies.
   - Match the repository's actual package manager, lockfiles, version pins, and setup flow.
   - For Python repos, prefer `astral-sh/setup-uv` with `python-version` so uv owns Python setup and dependency bootstrap in one path; then use `uv sync --frozen` plus `uv tool install` for repo-relevant developer tools such as `basedpyright`, `ruff`, and `ty`.
   - For Bun repos, prefer real Bun dependencies and global tools that the repo actually uses. In this repo, `@biomejs/biome`, `oxfmt`, and `oxlint` are valid; do not add an invalid `oxc` package dependency.
4. Create or update `.github/instructions/*.instructions.md`.
   - Add files only when the repository has a real language, workflow, review,
     or platform need.
   - Keep each file focused, reusable, and narrow in scope.
   - Avoid duplicating repo-wide guidance that belongs in the canonical guide.
5. Create or update `.github/skills/*/SKILL.md`.
   - Add only reusable skills tied to real repository workflows.
   - Give each skill a clear trigger, narrow scope, and concrete steps.
   - Call out generated files, unsafe areas, validation requirements, and any repo-specific invariants.
6. Create or update lint/check/test workflows when needed.
   - Reuse existing workflows when they already cover the repo.
   - Add the smallest workflow set that gives useful validation for the actual stack.
   - Prefer one tool per concern unless the repository already combines them.
   - Use project-relevant tools only:
     - JS/TS: `@biomejs/biome`, `oxlint`, `oxfmt`
     - Python: `basedpyright`, `ruff`, `ty`, `pytest`
     - Shell: `shellcheck`, `shfmt`, `shellharden`
     - PowerShell: PowerShell Editor Services or equivalent LSP plus repo-relevant lint and format tooling
     - Rust: `cargo check` and editor/LSP tooling such as `rust-analyzer`
   - If the repository does not contain a language, do not add its workflow, setup steps, or instructions.
7. Validate the result.
   - Verify every referenced path, file, and command exists.
   - Run the repository's existing validation for changed workflows and tracked files.
   - Do not claim runtime or end-to-end validation you did not perform.

## Portability requirements

- Tailor versions, dependencies, and commands to the current repository.
- Preserve good existing guidance files instead of replacing them wholesale.
- Respect the repository's chosen canonical guidance file names and structure.
- Prefer the smallest file set that still gives high-signal guidance.
- Keep the output useful even when a repository does not use `AGENTS.md` or `CLAUDE.md`.

## Guardrails

- Never invent commands, paths, dependencies, or workflows.
- Do not hand-edit generated artifacts when the repository provides a script or generator.
- Keep guidance concise, actionable, and repository-specific.
- Update good existing files instead of creating duplicates.
- When uv is the Python toolchain, prefer a single `astral-sh/setup-uv` step with `python-version` over combining uv with a separate `actions/setup-python` step unless the repository already requires both.
- Do not broaden validation scope just because a tool is popular. Implement only the linting, type-checking, formatting, and tests that the project actually needs.
- Use this split when deciding where guidance belongs:
  - Startup bootstrap: `.github/copilot-instructions.md`
  - Canonical repo-wide guide: whichever existing file the repository uses
  - Path- or topic-specific rules: `.github/instructions/*.instructions.md`
  - Reusable task workflow: `.github/skills/*/SKILL.md`
  - CI validation workflows: focused `.github/workflows/*.yml` files that match the repository's real stack

## Deliverables checklist

- `copilot-setup-steps` matches the repository's real setup path.
- Added or updated lint/check/test workflows match the repository's actual languages and commands.
- Instructions reflect the real stack, commands, and hotspots.
- Skills reflect recurring repository workflows.
- Large rule blocks are not duplicated across files.
- All changed files are internally consistent.
