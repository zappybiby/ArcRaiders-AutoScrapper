# Arc Raiders Inventory Auto Scrapper

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff) [![Maintainability](https://qlty.sh/gh/Ven0m0/projects/arc-raiders-autoscrapper/maintainability.svg)](https://qlty.sh/gh/Ven0m0/projects/arc-raiders-autoscrapper)
<p align="center">
 <img src="https://github.com/user-attachments/assets/c1de27b2-4dd9-4d04-855a-b4faa4e9dd1a" alt="autoscrapper_logo4">
</p>

Automates Arc Raiders inventory actions (Sell/Recycle) using screen capture and Tesseract (OCR).

This program does not hook into the game process, but there is no guarantee it will not be flagged by anti-cheat systems or violate the game's Terms of Service. Use at your own risk.

## Setup

This repo uses uv to manage Python + dependencies.

`uv sync` is enough for cloud/CI tasks that only need the project plus dev tooling.
Linux desktop automation also needs the optional linux-input extra, which the setup script installs for you.
The repo is pinned to Python 3.13 via .python-version.

### Clone the repo

From a terminal:

- `git clone https://github.com/Ven0m0/arc-raiders-autoscrapper.git`
- `cd arc-raiders-autoscrapper`

### Windows 10/11 (64-bit)

From the repo root, run the setup script

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1`

- Use a different supported Python version:
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -PythonVersion 3.13`

### Linux

`bash scripts/setup-linux.sh`
`PYTHON_VERSION=3.13 bash scripts/setup-linux.sh`
Manual full Linux install:
`uv sync --extra linux-input`

## Usage

Open the Textual UI (default):

- `uv run autoscrapper`

Start a scan directly:

- `uv run autoscrapper scan --dry-run`

scan only supports the optional --dry-run flag. Other workflows are in the Textual UI.

How AutoScrapper Works:
Open your inventory and make sure you are scrolled to the top of it
Start the scan, then alt-tab back into the game. It will then begin after a few seconds.
Press the configured stop key (default Esc) to abort (may need multiple presses).

Linux notes:

- Default target window title is `Arc Raiders`. Override with AUTOSCRAPPER_TARGET_APP if needed.

## Automated Data Updates

This repo includes a scheduled GitHub Action that refreshes game data and default rules daily.

Workflow: `.github/workflows/daily-data-update.yml`
Schedule: daily at `14:00 UTC`
Output: updates snapshot data + items_rules.default.json, then opens/updates a PR on branch `bot/daily-data-update`
Report: attaches `artifacts/update-report.json` and uses `artifacts/update-report.md` as PR body

The default rules are regenerated with this baseline:

- all quests completed
- workshop profile at level 2 for scrappy, weapon_bench, equipment_bench, med_station, explosives_bench, utility_bench, and refiner

### Data sources

The updater uses a primary API source plus a repository fallback so snapshot
refreshes stay usable when upstream data is incomplete or temporarily
unavailable.

[MetaForge ARC Raiders API docs](https://metaforge.app/arc-raiders/api), Purpose=Primary item and quest source, Behavior in AutoScrapper=Reads paginated items and quests responses from `https://metaforge.app/api/arc-raiders`
METAFORGE_SUPABASE_ANON_KEY + MetaForge Supabase tables, Purpose=Optional crafting and recycle relationships, Behavior in AutoScrapper=Adds recipe and recyclesInto data when the anon key is available
[fgrzesiak arcraiders-data](https://github.com/fgrzesiak/arcraiders-data), Purpose=Supplemental and fallback item and quest source, Behavior in AutoScrapper=Merges missing records into MetaForge results, or replaces missing datasets when MetaForge is unavailable
[Arc Raiders Wiki loot table](https://arcraiders.wiki/wiki/Loot), Purpose=Optional workshop/expedition/project-use enrichment, Behavior in AutoScrapper=Adds a wikiUses field to each item when the scraper extra is installed

### MetaForge API reference

MetaForge publishes the ARC Raiders endpoint documentation at
`https://metaforge.app/arc-raiders/api`. The updater follows that reference and
uses the API base URL `https://metaforge.app/api/arc-raiders`.

The current snapshot refresh reads these endpoints:

- `GET /items?page=<page>&limit=<limit>` for item records and pagination

  metadata

- `GET /quests?page=<page>&limit=<limit>` for quest records, reward items, and

  requirement payloads

MetaForge notes that these endpoints can change or break without warning and
asks consumers to cache results locally. AutoScrapper follows that guidance by
querying MetaForge only during snapshot refreshes, then reading the generated
JSON files at runtime instead of calling the API while scanning.

If you reuse this updater or publish derived data, keep MetaForge attribution
and link back to `https://metaforge.app/arc-raiders`, as required by the API
terms.

### fgrzesiak fallback

The updater also downloads the
[`fgrzesiak/arcraiders-data`](https://github.com/fgrzesiak/arcraiders-data)
repository archive during refreshes. AutoScrapper normalizes the item and quest
JSON files from that repository and uses them in two cases:

1. It appends item or quest records that are missing from the MetaForge API.
2. It falls back to the fgrzesiak dataset when a MetaForge item or quest fetch

   fails.

MetaForge remains the preferred source when both providers return the same
record ID. Generated metadata.json records which provider supplied the final
item and quest datasets.

### Arc Raiders Wiki enrichment

When the optional scraper extra is installed (`uv sync --extra scraper`), the
updater also fetches the [Arc Raiders Wiki loot table](https://arcraiders.wiki/wiki/Loot)
and enriches each item with a wikiUses field containing workshop upgrade
requirements, expedition requirements, and project-use data scraped from the
Uses column of the loot table.

MetaForge remains the authoritative source for items, sell prices, stack sizes,
recycle components, and quests. Wiki enrichment adds supplemental data only;
it does not replace any MetaForge field. A failed wiki fetch is logged as a
warning and the update continues without wiki data. The metadata.json
dataSources.items.wikiEnrichment block records the URL, whether the library
was available, how many items received a wikiUses value, and any error.

### Run updater locally

Use these commands from the repository root when you want to refresh generated
data on demand.

- Install the optional MetaForge anon key only if you want crafting and recycle

  component enrichment:

- `export METAFORGE_SUPABASE_ANON_KEY=...`
- Install the optional scraper extra to enable Arc Raiders Wiki enrichment

  (wikiUses field on items):
`uv sync --extra scraper`
Real update (writes tracked files):
Dry run (no tracked file writes):
`uv run python scripts/update_snapshot_and_defaults.py --dry-run`
