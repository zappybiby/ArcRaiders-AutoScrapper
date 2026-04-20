---

applyTo: "**/{*.py,pyproject.toml}"

## Python toolchain

- Target Python 3.13 only; the repo is pinned via `.python-version` and

  `pyproject.toml`.

- Install dependencies with `uv sync`; use `uv sync --extra linux-input` only

  when Linux input automation is required.

- Format with `uv run ruff format src/ tests/ scripts/`.
- Type-check with `uv run basedpyright src/`.
- Test with `uv run pytest`.

## Style and typing

- Match the repository's Ruff formatting: 120-character lines and double

  quotes.

- Add explicit type hints to public functions and dataclass fields.
- Prefer `T | None` over `Optional[T]`.
- Use `pathlib`, context managers, and specific exceptions.
- Keep business logic simple and avoid hidden global state.

## Repo invariants

- Preserve custom-over-default rule precedence.
- Do not hand-edit `src/autoscrapper/progress/data/*` or

  `src/autoscrapper/items/items_rules.default.json`; regenerate them with
  `uv run python scripts/update_snapshot_and_defaults.py`.

- Bump `CONFIG_VERSION` and add a migration when persisted config fields

  change.

- `initialize_ocr()` must run on the main thread before scan threads start.
- Capture-space image coordinates must stay separate from screen-space input

  coordinates.

- `inventory_vision.py` upscales OCR images 2x; convert OCR boxes back to

  original-space coordinates before reusing them.

- Keep OCR item-name matching and rule lookup on the same fuzzy-match

  threshold.

## Validation

- Python source changes: run Ruff, BasedPyright, and pytest.
- OCR, scanner, interaction, or input changes: also run

  `uv run autoscrapper scan --dry-run` against a live Arc Raiders window.

- Do not claim end-to-end validation unless a live game window was used.
