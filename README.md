# Arc Raiders Inventory Auto Scrapper

Walks through each inventory item and applies Sell/Recycle decisions using only screenshots and OCR. It never hooks the game process, memory, or network; everything is screen capture plus simulated mouse input.

## How it works
- Captures the active Arc Raiders window via MSS and PyWinCtl auto-detects which monitor the game is on (windowed, borderless, or fullscreen).
- Finds the item infobox, OCRs the title, and looks up the decision from your rules file (`src/autoscrapper/items/items_actions.json` in this repo).
- Executes Sell/Recycle depending on the recommended action.
- Press Escape to cancel (may need a couple presses).

## Setup
Windows 10/11 and Ubuntu (native X11/XWayland) are supported. WSL is not supported.

Python 3.10–3.13 is supported (3.13 recommended). Python 3.14 is not supported.

This repo uses `uv` to manage Python + dependencies. `tesserocr` is a required dependency:
- Windows installs `tesserocr` via the matching prebuilt wheel from GitHub (handled automatically by `uv`).
- Linux installs `tesserocr` from PyPI and requires system `tesseract`/`leptonica` dev packages (the Linux setup script installs them).
- Input injection uses `pydirectinput-rgx` on Windows and `pynput` on Linux.

### Clone the repo
From a terminal (PowerShell/CMD on Windows, bash on Linux):
- `git clone https://github.com/zappybiby/ArcRaiders-AutoScrapper.git`
- `cd ArcRaiders-AutoScrapper`

### Windows 10/11 (64-bit)
From the repo root:
- PowerShell: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1`
- CMD: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1`
- Optional (use a different supported Python):
  - PowerShell: add `-PythonVersion 3.12`
  - CMD: add `-PythonVersion 3.12`

### Ubuntu / Debian (native X11/XWayland)
From the repo root:
- `bash scripts/setup-linux.sh`
- Optional (use a different supported Python): `AUTOSCRAPPER_PYTHON_VERSION=3.12 bash scripts/setup-linux.sh`

## Usage

Launch options:

```
uv run autoscrapper           # Interactive menu
uv run autoscrapper scan      # Start the inventory scan directly
uv run autoscrapper rules     # Open the item rules editor
uv run autoscrapper progress  # Stub for future progress editing
uv run autoscrapper config    # Edit scan configuration (persisted)
```

Typical scan flow:
1) In Arc Raiders, open your inventory (ideally the “Crafting Materials” tab). Make sure you are scrolled all the way up and the game window is entirely on one monitor.
2) Run: `uv run autoscrapper scan`
3) Alt-tab back into Arc Raiders quickly; after a few seconds the script will log the display it detected and start processing.
4) Press Escape to abort (may need to press a few times).

Linux note: this assumes a native Ubuntu desktop with the game window running under X11/XWayland (Proton is fine). Pure Wayland sessions may not support window detection or input injection.
The Linux default target is the window title `Arc Raiders`. You can override it with `AUTOSCRAPPER_TARGET_APP` if needed.

### Dry run
See what the script would do without clicking Sell/Recycle (logs planned decisions such as `SELL`/`RECYCLE`):

```bash
uv run autoscrapper scan --dry-run
```

## Scan configuration
The interactive menu includes **Scan configuration** to persist scan defaults for future runs (pages, scroll clicks, debug OCR, profiling).
By default, if an item title OCR is unreadable, the scanner retries once after 100ms; you can change this in **Scan configuration**.

You can also run it directly: `uv run autoscrapper config`. CLI flags always override the saved defaults for that run.

Settings are stored at `%APPDATA%\AutoScrapper\config.json` on Windows, and `~/.autoscrapper/config.json` on Linux.

## Item rules CLI
Manage the keep/recycle/sell rules stored in `src/autoscrapper/items/items_actions.json`:

```bash
uv run autoscrapper rules
```

You can view all rules, view a specific item by name or index, add new items, edit existing ones, or remove entries.

## CLI options (scan)
- `--pages INT` override auto-detected 6x4 page count to scan.
- `--scroll-clicks INT` initial scroll clicks between grids (alternates with +1 on the next page).
- `--dry-run` log planned actions without clicking Sell/Recycle.
- `--profile` enable per-item timing logs (capture, OCR, total).
- `--no-profile` disable per-item timing logs (overrides saved scan configuration).
- `--debug` / `--debug-ocr` save OCR debug images to `./ocr_debug`.
- `--no-debug` disable OCR debug images (overrides saved scan configuration).

## Contributing
Black is the formatter for this codebase and should be used for all contributions.
- Install: `uv pip install black`
- Format a file: `uv run python -m black path/to/file.py`
