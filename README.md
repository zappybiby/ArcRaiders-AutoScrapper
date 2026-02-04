<p align="center">
  <img src="https://github.com/user-attachments/assets/c1de27b2-4dd9-4d04-855a-b4faa4e9dd1a" alt="autoscrapper_logo4">
</p>



## Arc Raiders Inventory Auto Scrapper

Automates Arc Raiders inventory actions (Sell/Recycle) using screen capture and Tesseract (OCR).

**This program does not hook into the game process, but there is no guarantee it will not be flagged by anti-cheat systems or violate the game’s Terms of Service. Use at your own risk.**

## Setup
This repo uses `uv` to manage Python + dependencies.

### Clone the repo
From a terminal:
- `git clone https://github.com/zappybiby/ArcRaiders-AutoScrapper.git`
- `cd ArcRaiders-AutoScrapper`

### Windows 10/11 (64-bit)
**From the repo root, run the setup script**

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1`

- **Use a different supported Python version**:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -PythonVersion 3.12`

### Linux
**From the repo root, run the setup script**

`bash scripts/setup-linux.sh`
- **Use a different supported Python version**:
  - `AUTOSCRAPPER_PYTHON_VERSION=3.12 bash scripts/setup-linux.sh`

## Usage

Open the Textual UI (default):
- `uv run autoscrapper`

Open the Textual UI explicitly:
- `uv run autoscrapper tui`

Start a scan directly:
- `uv run autoscrapper scan`

`scan` is the only standalone CLI command. Other workflows are now in the Textual UI.

How AutoScrapper Works:
- Open your inventory and make sure you are scrolled to the top of it
- Start the scan, then alt-tab back into the game. It will then begin after a few seconds.
- Press Escape to abort (may need multiple presses).

Linux notes:
- Default target window title is `Arc Raiders`. Override with `AUTOSCRAPPER_TARGET_APP` if needed.
