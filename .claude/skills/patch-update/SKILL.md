---
name: patch-update
description: Use when user wants to Full new-game-patch pipeline — fetch Metaforge data, regenerate default rules, run verify, report items with no rule coverage.
---

Run after a game patch or when Metaforge data is known to have changed.

## Step 1 — Dry-run first

```bash
uv run python scripts/update_snapshot_and_defaults.py --dry-run
```

Review the diff. If only timestamps changed (no item/quest/rule deltas), stop — nothing to do.

## Step 2 — Apply update

```bash
uv run python scripts/update_snapshot_and_defaults.py
```

Protected files updated automatically:
- `src/autoscrapper/progress/data/items.json`
- `src/autoscrapper/progress/data/quests_by_trader.json`
- `src/autoscrapper/progress/data/metadata.json`
- `src/autoscrapper/items/items_rules.default.json`

Do not hand-edit these files.

## Step 3 — Check rule coverage gaps

After regeneration, identify items present in the new snapshot that have no custom rule:

```bash
uv run python - <<'EOF'
import orjson
from pathlib import Path

items = orjson.loads(Path("src/autoscrapper/progress/data/items.json").read_bytes())
rules = orjson.loads(Path("src/autoscrapper/items/items_rules.default.json").read_bytes())

rule_names = {r["item_name"] for r in rules.get("rules", [])}
no_rule = [i["name"] for i in items if i.get("name") and i["name"] not in rule_names]

if no_rule:
    print(f"{len(no_rule)} items with no rule:")
    for n in sorted(no_rule):
        print(f"  {n}")
else:
    print("All items have rule coverage.")
EOF
```

For each gap item, use `/add-rule` to assign a KEEP/SELL/RECYCLE action.

## Step 4 — Validate

```bash
uv run ruff check src/ tests/
uv run basedpyright src/
uv run pytest
```

All three must pass before committing. Then use `/ci-promote` to push.
