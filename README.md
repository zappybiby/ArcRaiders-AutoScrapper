# Arc Raiders Inventory Auto Scrapper

Lightweight helper that walks the 4x6 inventory grid and applies Sell/Recycle decisions using only screenshots and OCR. It never hooks the game process, memory, or network; everything is screen capture plus simulated mouse input.

## How it works
- Captures the active Arc Raiders window, finds the item infobox, OCRs the title, and looks up the decision from `items/items_actions.json`.
- Executes Sell/Recycle clicks when configured; in dry-run mode it only logs actions.
- Press Escape to cancel (may need a couple presses if the game is busy).

## Setup
1) Install Python 3 and dependencies: `pip install -r requirements.txt`.
2) Ensure `mss` or `pyautogui` is available for screenshots (included in requirements).

## Usage
1) In Arc Raiders, open your inventory (ideally the “Crafting Materials” tab).
2) Run: `python3 inventory_scanner.py`
3) Alt-tab back into Arc Raiders; after a few seconds the script will start processing.
4) Press Escape to abort.

### Dry run
Log decisions without clicking Sell/Recycle:

```bash
python3 inventory_scanner.py --dry-run
```
