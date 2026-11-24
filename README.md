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
Requires [Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vc14/vc_redist.x64.exe).

**From the repo root, run the setup script**

In PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
.\scripts\setup-windows.ps1
```

### Linux
**From the repo root, run the setup script**

`bash scripts/setup-linux.sh`

## Usage

Open the Textual UI (default):
- `uv run autoscrapper`

Start a scan directly:
- `uv run autoscrapper scan`
- `uv run autoscrapper scan --dry-run`

`scan` only supports the optional `--dry-run` flag. Other workflows are in the Textual UI.

How AutoScrapper Works:
- Open your inventory and make sure you are scrolled to the top of it
- Start the scan, then alt-tab back into the game. It will then begin after a few seconds.
- Press the configured stop key (default Esc) to abort (may need multiple presses).

Linux notes:
- Default target window title is `Arc Raiders`. Override with `AUTOSCRAPPER_TARGET_APP` if needed.

## Automated Data Updates

This repo includes a scheduled GitHub Action that refreshes game data and default rules daily.

- Workflow: `.github/workflows/daily-data-update.yml`
- Schedule: daily at `14:00 UTC`
- Output: updates snapshot data + `items_rules.default.json`, then opens/updates a PR on branch `bot/daily-data-update`
- Report: attaches `artifacts/update-report.json` and uses `artifacts/update-report.md` as PR body

The default rules are regenerated with this baseline:
- all quests completed
- workshop profile at level 2 for `scrappy`, `weapon_bench`, `equipment_bench`, `med_station`, `explosives_bench`, `utility_bench`, and `refiner`

### Run updater locally

- Real update (writes tracked files):
  - `uv run python scripts/update_snapshot_and_defaults.py`
- Dry run (no tracked file writes):
  - `uv run python scripts/update_snapshot_and_defaults.py --dry-run`
