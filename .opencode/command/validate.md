# Validate Changes

Run appropriate validation based on change type.

## Change Types

- Python source: `uv run ruff check src/`
- Broad repo: `uv run prek run --all-files`
- OCR/scanner: `uv run autoscrapper scan --dry-run`
- Generated data: `uv run python scripts/update_snapshot_and_defaults.py --dry-run`

## Debug Output

After OCR changes, inspect `ocr_debug/`:

- `*_infobox_detect_overlay.png`, `*_ctx_menu_processed.png`, `*_infobox_action_sell_processed.png`
