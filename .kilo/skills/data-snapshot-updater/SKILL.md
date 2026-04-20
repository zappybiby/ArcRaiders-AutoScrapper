---
name: data-snapshot-updater
description: Use when user wants to Update Metaforge snapshots and bundled default rules
context: fork
---

# Data Snapshot Updater Skill

Refresh Arc Tracker / Metaforge data snapshots and regenerate bundled default item rules.

## When to Use

- After upstream data changes (Arc Tracker Metaforge update)
- When adding/updating bundled default rules
- After game patches that change item names or trader quests
- When default keep/sell/recycle decisions are stale
- Before committing if `progress/data/*.json` or `items_rules.default.json` appear modified in `git status`
- Daily cycle maintenance (or as part of CI automation)
- After manually editing quest/item metadata

## Usage

```bash

# Dry-run: show what would change without writing
/data-snapshot-updater --dry-run

# Update live (fetch from Arc Tracker, regenerate rules, report changes)
/data-snapshot-updater

# Verbose: include detailed diff of each file
/data-snapshot-updater --verbose
```

## What It Does

1. Fetches latest Arc Tracker Metaforge snapshot via API
2. Merges with existing cached data (preserves custom overrides)
3. Detects substantive changes (ignores timestamp-only updates)
4. Regenerates `items_rules.default.json` from current item/quest state
5. Produces markdown + JSON report of changes
6. (In CI) Auto-commits and opens PR if changes detected

## Behind the Scenes

Runs: `uv run python scripts/update_snapshot_and_defaults.py [--dry-run]`

Protected files (auto-generated-do not hand-edit):

- `src/autoscrapper/progress/data/quests_by_trader.json`
- `src/autoscrapper/items/items_rules.default.json`

## Validation

- Config version bump on schema changes
- Quest inference correctness
- Custom rule precedence preserved
- Stale data detection (gaps in quest/hideout/crafting data)
- No hand-edits to protected files

*Invoke with `/data-snapshot-updater [--dry-run]` for data maintenance.*
