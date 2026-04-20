---

applyTo: ".github/workflows/*.yml"

## Workflow defaults

- Keep triggers minimal. For setup-only workflows, use `workflow_dispatch` plus

  `push` and `pull_request` scoped to the workflow file.

- Set the smallest possible `permissions:` block. Read-only workflows should

  use `contents: read`.

- Pin actions to version tags already used in this repo, such as

  `actions/checkout@v6`, `astral-sh/setup-uv@v7`, and
  `actions/upload-artifact@v7`.

- Set `persist-credentials: false` on checkout unless the workflow must push

  back to the repository.

## Python repository setup

- Prefer `astral-sh/setup-uv@v7` with `python-version: "3.13"`.
- Cache both `uv.lock` and `pyproject.toml`.
- Prefer `uv sync --frozen` for general-purpose setup. Add extras only when the

  workflow truly needs them.

- Avoid `--all-extras` in general bootstrap workflows; it pulls optional stacks

  that are not required for most tasks.

- Install only the apt packages the workflow actually needs. Common OCR build

  dependencies are `build-essential`, `pkg-config`, `tesseract-ocr`,
  `libtesseract-dev`, and `libleptonica-dev`. Add `libevdev-dev` only when the
  workflow needs Linux input or evdev builds.

## Validation and security

- Validate workflow edits with `uv run prek run --files .github/workflows/<name>.yml`.
- Fix Zizmor findings instead of suppressing them when a safe workflow change is

  available.

- Do not install unrelated tooling in setup workflows; keep Copilot bootstrap

  jobs aligned with the repository's real stack.
