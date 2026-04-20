---
name: update-data
description: Use when user wants to Safely regenerate progress/data/*.json and items_rules.default.json via the update script
---

Generated data files must **never** be hand-edited. Always regenerate via the script:

```bash
# Preview changes first (safe, no writes)
uv run python scripts/update_snapshot_and_defaults.py --dry-run

# Apply if the preview looks correct
uv run python scripts/update_snapshot_and_defaults.py
```

**Files this script controls:**
- `src/autoscrapper/progress/data/items.json`
- `src/autoscrapper/progress/data/metadata.json`
- `src/autoscrapper/progress/data/quests.json`
- `src/autoscrapper/progress/data/quests_by_trader.json`
- `src/autoscrapper/items/items_rules.default.json`

**Custom rules are safe** — the script only regenerates defaults. Custom rules in `items_rules.json` are never touched.

**When to run:**
- After game patches that change item names or trader quests
- When default keep/sell/recycle decisions are stale
- Before committing if any of the above files show as modified in `git status`

**Do not** commit modified generated files without running this script first — hand-edited JSON will be overwritten on the next scheduled run.
