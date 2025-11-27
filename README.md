# Arc Raiders Inventory Auto Scrapper

Walks through each inventory item and applies Sell/Recycle decisions using only screenshots and OCR. It never hooks the game process, memory, or network; everything is screen capture plus simulated mouse input.

## How it works
- Captures the active Arc Raiders window, finds the item infobox, OCRs the title, and looks up the decision from `items/items_actions.json`.
- Executes Sell/Recycle depending on the recommended action.
- Press Escape to cancel (may need a couple presses)

## Setup
1) Install dependencies: `pip install -r requirements.txt`.
2) You need [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki#tesseract-installer-for-windows) installed. The script auto-detects common Windows install paths and the PATH entry; set `TESSERACT_CMD` to the full `tesseract.exe` path if you installed it elsewhere.

## Tesseract detection
- On startup the script tries, in order: `TESSERACT_CMD` env var (if set), `tesseract.exe`/`tesseract` on `PATH`, registry hints, and common install folders such as `C:\Program Files\Tesseract-OCR\tesseract.exe`, `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`, and `%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe`.
- To override manually (per-shell session):
  - Windows Terminal / PowerShell: `$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'`
  - cmd.exe: `set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`
- Keep the full path in quotes if it contains spaces.

## Usage
Main entrypoint: run `inventory_scanner.py` from the repo root.

1) In Arc Raiders, open your inventory (ideally the “Crafting Materials” tab). Make sure you are scrolled all the way up.
2) Run: `python3 inventory_scanner.py`
3) Alt-tab back into Arc Raiders; after a few seconds the script will start processing.
4) Press Escape to abort (may need to press a few times).

### Dry run
See what the script would do without clicking Sell/Recycle (logs planned decisions such as `SELL`/`RECYCLE`):

```bash
python3 inventory_scanner.py --dry-run
```
