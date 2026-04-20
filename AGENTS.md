This file is the canonical repository guide for contributors and coding
agents working in Arc Raiders AutoScrapper. Keep `CLAUDE.md` as a symlink
to this file. Keep `.github/copilot-instructions.md` short and startup-
focused, and put path-specific rules in `.github/instructions/*.instructions.md`.

## Start here

Read this file before you edit code, workflows, or agent guidance. It gives
you the repository map, the validation commands, and the rules that must stay
true across OCR, scanner, interaction, and config changes.

- Use Python 3.13.
- Prefer `python3 -m uv ...` in automation because `uv` may not be on `PATH`.
- Keep edits minimal and repo-specific.
- Use script-driven updates for generated assets instead of hand edits.
- Verify every command, file path, and link you touch.

## Project overview

Arc Raiders AutoScrapper is a desktop automation app for Arc Raiders inventory
management. It uses Textual for the TUI, screen capture plus OCR for item
detection, rule lookup for `KEEP | SELL | RECYCLE`, and optional desktop input
automation. It does not hook into the game process.

| Area | Details |
| --- | --- |
| Runtime | Python 3.13, `uv` |
| UI | `textual` |
| OCR | `tesserocr`, `tessdata.fast-eng` |
| Vision | `opencv-python-headless`, `Pillow`, `mss` |
| Matching | `rapidfuzz` |
| Input | `pydirectinput-rgx` on Windows, `pynput` via `linux-input` on Linux |

## Repository map

Use this map to find the right module before editing. The OCR, interaction,
and scanner paths are tightly coupled, so read adjacent modules before you
change behavior there.

| Path | Purpose |
| --- | --- |
| `src/autoscrapper/tui/` | Textual screens; `scan.py` starts the scan flow |
| `src/autoscrapper/scanner/` | Scan engine, page loop, reporting, action execution |
| `src/autoscrapper/interaction/` | Screen capture, grid detection, platform input |
| `src/autoscrapper/ocr/` | Tesseract init, preprocessing, infobox and item extraction |
| `src/autoscrapper/core/item_actions.py` | Rule lookup and fuzzy decision logic |
| `src/autoscrapper/items/rules_store.py` | Load and save custom rules; custom overrides bundled defaults |
| `src/autoscrapper/progress/` | Quest, hideout, crafting data and default-rule generation |
| `scripts/update_snapshot_and_defaults.py` | Regenerates bundled progress data and default rules |
| `src/autoscrapper/config.py` | Persisted config dataclasses and versioning |
| `tests/` | Pytest suite |

## Setup and daily commands

Use these commands as the source of truth for local setup, validation, and
safe data refresh tasks.

| Task | Command |
| --- | --- |
| Install dependencies | `python3 -m uv sync` |
| Install Linux input extra | `python3 -m uv sync --extra linux-input` |
| Run the TUI | `python3 -m uv run autoscrapper` |
| Run a scan | `python3 -m uv run autoscrapper scan` |
| Run a safe dry-run scan | `python3 -m uv run autoscrapper scan --dry-run` |
| Lint Python | `python3 -m uv run ruff check src/ tests/ scripts/` |
| Format Python | `python3 -m uv run ruff format src/ tests/ scripts/` |
| Type-check Python | `python3 -m uv run basedpyright src/` |
| Run tests | `python3 -m uv run pytest` |
| Validate workflows | `python3 -m uv run prek run --files .github/workflows/<name>.yml` |
| Run broad repo checks | `python3 -m uv run prek run --all-files` |
| Refresh generated data and rules | `python3 -m uv run python scripts/update_snapshot_and_defaults.py` |
| Dry-run data refresh | `python3 -m uv run python scripts/update_snapshot_and_defaults.py --dry-run` |

If `python3 -m uv run <cmd>` fails with `No module named uv`, use
`uv run <cmd>` directly.

## Validation expectations

Run the smallest validation set that fully covers your change. For Python code,
run lint, types, and tests. For workflows, run the workflow-specific `prek`
check. For docs and guidance, verify that the referenced files, commands, and
links are accurate.

| Change type | Minimum validation |
| --- | --- |
| Python source | `python3 -m uv run ruff check src/ tests/ scripts/` + `python3 -m uv run basedpyright src/` + `python3 -m uv run pytest` |
| Workflow files | `python3 -m uv run prek run --files .github/workflows/<name>.yml` |
| Generated data or default rules | Use the updater script, usually with `--dry-run` first |
| Docs or agent guidance only | Verify affected paths, commands, links, and instruction hierarchy |
| OCR, scanner, interaction, or input behavior | Standard Python validation plus `python3 -m uv run autoscrapper scan --dry-run` against a live Arc Raiders window |

Do not claim end-to-end OCR or scanner validation unless you used a real Arc
Raiders window. Prefer `--dry-run` before anything that could click in-game.

## Generated files and persisted config

These rules prevent accidental drift in generated assets and saved user state.
Follow them any time you touch progress data, item rules, or persisted config.

- Do not hand-edit `src/autoscrapper/progress/data/*`.
- Do not hand-edit `src/autoscrapper/items/items_rules.default.json`.
- Regenerate both through `scripts/update_snapshot_and_defaults.py`.
- When persisted config fields change, bump `CONFIG_VERSION` in
  `src/autoscrapper/config.py` and add a migration.
- Preserve custom-over-default rule precedence.

## OCR and interaction invariants

These are the highest-risk behavior rules in the repository. Changes in these
areas need extra caution and often need live validation or corpus replay.

- `initialize_ocr()` must run on the main thread before scan threads start.
- Keep the four Tesseract API locks separate: `_api_lock`, `_api_line_lock`,
  `_api_single_word_lock`, and `_api_sparse_lock`.
- Keep capture-space image coordinates separate from screen-space input
  coordinates. Screen translation belongs in
  `src/autoscrapper/interaction/ui_windows.py`.
- `inventory_vision.py` upscales OCR images by 2x. Convert OCR boxes back to
  original-space coordinates before you reuse them.
- The dark context menu opens to the left of the clicked cell. The
  `_CONTEXT_MENU_*` constants in `inventory_vision.py` are normalized by 1920.
- Prefer `ocr_infobox_with_context(window_bgr, rect)` when the full window is
  available.
- `find_context_menu_crop` rejects crops with `dark_fraction < 0.20` on the
  left half. Treat that threshold as calibration-sensitive.
- Keep the fuzzy-match threshold shared between OCR item matching and rule
  lookup. Changing threshold or `score_cutoff` values requires corpus replay
  before shipping.

## Hotspots

Focus extra review time on these files and modules because they drive the most
critical behavior.

- `src/autoscrapper/ocr/inventory_vision.py`
- `src/autoscrapper/ocr/`
- `src/autoscrapper/interaction/`
- `src/autoscrapper/scanner/`
- `src/autoscrapper/core/item_actions.py`
- `src/autoscrapper/items/rules_store.py`
- `src/autoscrapper/config.py`

## Copilot and agent guidance

Use the smallest guidance surface that fits the task. Keep startup guidance
short, and move detailed rules into stable repo files.

- Treat this file as the canonical long-form guide.
- Keep `.github/copilot-instructions.md` short and focused on startup.
- Put path-specific rules in `.github/instructions/*.instructions.md`.
- Keep `.github/workflows/copilot-setup-steps.yml` aligned with the real
  bootstrap path: `actions/checkout@v6`, `astral-sh/setup-uv@v7`, OCR system
  packages, and `uv sync --frozen`.
- Reuse existing workflows instead of adding overlapping CI or validation jobs.
- Do not broaden setup or CI to optional extras unless the workflow actually
  needs them.

## Preferred skills and specialist reviews

Use the existing skills and reviewer agents instead of inventing new guidance
or duplicate workflows. Start with the repo-wide skills, then add a specialist
only when the task touches a hotspot.

### GitHub Copilot skills

Use these first when they match the task:

- `mcp-use`
- `language-optimization`
- `codebase-index`
- `workflow-development`
- `docs-writer`
- `update-data`
- `validate`
- `lint-and-validate`
- `copilot-init`

### Claude skills and agents

If you are working in a Claude-style agent environment, these specialist tools
already exist in `.claude/skills/` and `.claude/agents/`.

- Use workflow skills such as `/verify`, `/data-snapshot-updater`,
  `/ocr-corpus-replay`, `/threshold-change`, `/config-bump`, and
  `/dead-code-sweep` when the task matches.
- Use reviewer agents such as `ocr-reviewer`, `scan-validator`,
  `rules-reviewer`, `config-reviewer`, `progress-reviewer`,
  `data-pipeline-reviewer`, `tui-reviewer`, and `security-reviewer` after
  hotspot edits.

## Documentation updates

When you update docs or agent guidance, keep the hierarchy clear. Put stable,
repo-wide rules here, keep startup instructions short in
`.github/copilot-instructions.md`, and avoid duplicating large rule blocks
across multiple files.
