# Repository Guidelines

Concise guide for contributing to the Arc Raiders inventory auto-scrapper. Keep changes small, tested, and readable.

## Project Structure & Module Organization
- `inventory_scanner.py`: main entrypoint; orchestrates grid walking, OCR, and Sell/Recycle actions.
- `grid_navigation.py`: grid geometry, contour detection, and safe mouse coordinates.
- `vision_ocr.py`: infobox detection, OCR utilities, and button coordinate helpers.
- `ui_backend.py`: window handling, mouse/scroll pacing, and click helpers.
- `inventory_domain.py`: decision logic and mapping from item names to actions (`items/items_actions.json`).
- `detect_tesseract.py`: resolves `pytesseract` path (env var, PATH, registry, or common installs).

## Setup, Build, and Run
- Install deps: `pip install -r requirements.txt`.
- Run full flow (with clicks): `python3 inventory_scanner.py`.
- Dry run (log planned decisions, no clicks): `python3 inventory_scanner.py --dry-run`.
- Ensure Tesseract is installed; override path per session with `TESSERACT_CMD="C:\\Program Files\\Tesseract-OCR\\tesseract.exe" python3 inventory_scanner.py`.

## Coding Style & Naming Conventions
- Python 3 with type hints; prefer explicit types and dataclasses for data containers.
- 4-space indentation; keep lines readable and avoid trailing whitespace.
- Constants are ALL_CAPS; helper functions use snake_case verbs (`open_cell_menu`, `scroll_to_next_grid_at`).
- Keep UI timings and ratios configurable via top-level constants; avoid magic numbers inline.

## Testing & Validation
- No automated test suite yet; validate manually:
  - `--dry-run` to review planned actions without input.
  - Full run on a small inventory page; verify infobox placement on bottom row and correct Sell/Recycle.
  - Remember the game slides items up after Sell/Recycle (vacated cell is filled by the next item); ensure grid traversal or pagination logic still aligns.
- If adding vision logic, capture before/after screenshots for sanity checks.

## Commit & Pull Request Guidelines
- Always commit after a change; push only when requested.
- Use short, imperative commit messages (e.g., `Adjust last row cell click position`, `Add Tesseract auto-detection helper`).
- For PRs, include: purpose, key changes, manual test notes (commands + outcomes), and any UI quirks to watch for.
- Mention if behavior changes depend on external configuration (Tesseract path, game resolution, or scrolling cadence).

## Security & Configuration Tips
- Tool is screen/automation-only; never hook game processes or network calls.
- Keep credentials out of code and logs; `.env` is not used—prefer environment variables for overrides.
