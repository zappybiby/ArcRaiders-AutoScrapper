# Patch Update

Full pipeline for new game patch or Metaforge data changes.

**Run after a game patch or when Metaforge data has changed.**

**Step 1 - Dry-run first:**
```bash
uv run python scripts/update_snapshot_and_defaults.py --dry-run
```
Review the diff. If only timestamps changed, stop - nothing to do.

**Step 2 - Apply update:**
```bash
uv run python scripts/update_snapshot_and_defaults.py
```
Protected files updated automatically:
- `src/autoscrapper/progress/data/quests_by_trader.json`
- `src/autoscrapper/items/items_rules.default.json`

**Step 3 - Check rule coverage gaps:**
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
        print(f" {n}")
else:
    print("All items have rule coverage.")
EOF
```

For each gap item, use `/add-rule` to assign KEEP/SELL/RECYCLE.

**Step 4 - Validate:**
```bash
uv run ruff check src/ tests/
uv run basedpyright src/
uv run pytest
```

Then use `/ci-promote` to push.

**Related:** Skills: `patch-update`, `data-snapshot-updater` | Agents: `data-pipeline-reviewer`, `progress-reviewer`
