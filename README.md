# Arc Raiders Inventory Auto Scrapper

Walks through each inventory item and applies Sell/Recycle decisions using only screenshots and OCR. It never hooks the game process, memory, or network; everything is screen capture plus simulated mouse input.

## How it works
- Captures the active Arc Raiders window via MSS and PyWinCtl auto-detects which monitor the game is on (windowed, borderless, or fullscreen).
- Finds the item infobox, OCRs the title, and looks up the decision from your rules file (`src/autoscrapper/items/items_actions.json` in this repo).
- Executes Sell/Recycle depending on the recommended action.
- Press Escape to cancel (may need a couple presses).

## Setup
Windows 10/11 is required (window detection + input automation rely on Windows APIs). Python 3.10 - 3.13 recommended.

1) Create and activate a virtualenv in the repo root:
   - `python -m venv .venv`
   - PowerShell: `.\\.venv\\Scripts\\Activate.ps1`
   - Command Prompt: `.\\.venv\\Scripts\\activate.bat`
2) Install tesserocr for your Python/Windows build:
   - Download the matching 64-bit wheel (e.g. `tesserocr-2.9.1-cp313-cp313-win_amd64.whl`) from https://github.com/simonflueckiger/tesserocr-windows_build/releases
   - Install it with `pip install <wheel_filename>.whl`
3) Install the package (and all other dependencies) in editable mode from the repo root:
   - `pip install -e .`

## Usage

Launch options (after the editable install):

```
python -m autoscrapper           # Interactive menu
python -m autoscrapper scan      # Start the inventory scan directly
python -m autoscrapper rules     # Open the item rules editor
python -m autoscrapper progress  # Stub for future progress editing
python -m autoscrapper config    # Edit scan configuration (persisted)
```

Typical scan flow:
1) In Arc Raiders, open your inventory (ideally the “Crafting Materials” tab). Make sure you are scrolled all the way up and the game window is entirely on one monitor.
2) Run: `python -m autoscrapper scan`
3) Alt-tab back into Arc Raiders quickly; after a few seconds the script will log the display it detected and start processing.
4) Press Escape to abort (may need to press a few times).

### Dry run
See what the script would do without clicking Sell/Recycle (logs planned decisions such as `SELL`/`RECYCLE`):

```bash
python -m autoscrapper scan --dry-run
```

## Scan configuration
The interactive menu includes **Scan configuration** to persist scan defaults for future runs (pages, scroll clicks, debug OCR, profiling).

You can also run it directly: `python -m autoscrapper config`. CLI flags always override the saved defaults for that run.

Settings are stored at `%APPDATA%\\AutoScrapper\\config.json` on Windows.

## Item rules CLI
Manage the keep/recycle/sell rules stored in `src/autoscrapper/items/items_actions.json`:

```bash
python -m autoscrapper rules
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
