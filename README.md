# Arc Raiders Inventory Auto Scrapper

Walks through each inventory item and applies Sell/Recycle decisions using only screenshots and OCR. It never hooks the game process, memory, or network; everything is MSS screen capture plus simulated mouse input.

## How it works
- Captures the active Arc Raiders window via MSS and PyWinCtl auto-detects which monitor the game is on (windowed, borderless, or fullscreen).
- Finds the item infobox, OCRs the title, and looks up the decision from `items/items_actions.json`.
- Executes Sell/Recycle depending on the recommended action.
- Press Escape to cancel (may need a couple presses)

## Setup
Windows 10/11 is required (MSS capture only). Keep Arc Raiders fully on a single monitor; PyWinCtl will log the detected display name and geometry automatically.

1) Install dependencies: `pip install -r requirements.txt`.
2) Install tesserocr for your Python/Windows build:
   - Download the matching 64-bit wheel (e.g. `tesserocr-2.9.1-cp313-cp313-win_amd64.whl`) from https://github.com/simonflueckiger/tesserocr-windows_build/releases
   - Install it with `pip install <wheel_filename>.whl`

## Usage

1) In Arc Raiders, open your inventory (ideally the “Crafting Materials” tab). Make sure you are scrolled all the way up and the game window is entirely on one monitor.
2) Run: `python inventory_scanner.py`
3) Alt-tab back into Arc Raiders quickly; after a few seconds the script will log the display it detected and start processing.
4) Press Escape to abort (may need to press a few times).

### Dry run
See what the script would do without clicking Sell/Recycle (logs planned decisions such as `SELL`/`RECYCLE`):

```bash
python inventory_scanner.py --dry-run
```

## Item rules CLI
Manage the keep/recycle/sell rules stored in `items/items_actions.json`:

```bash
python items/rules_cli.py
```

You can view all rules, view a specific item by name or index, add new items, edit existing ones, or remove entries.
