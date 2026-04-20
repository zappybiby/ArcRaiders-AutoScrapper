---
name: scan-failed
description: Use when user wants to Context for diagnosing scans where OCR read items correctly but sell/recycle decisions were wrong — rule precedence, fuzzy threshold, progress overrides
user-invocable: false
---

## When OCR is correct but the action was wrong

Check in this order:

1. **Custom rule loaded?** — `rules_store.py` loads custom rules from a user-configured path, falling back to bundled defaults if the file is missing. Confirm the custom file path is correct and the file exists.

2. **Rule precedence** — custom rules must override defaults. If a default rule is winning, the merge order in `item_actions.py` is inverted.

3. **Fuzzy threshold** — the threshold in `core/item_actions.py` must match the one used in OCR matching. If the item name passed to rule lookup has extra characters (common with infobox trailing spaces), low scores may fall below the threshold and cause a fallback to the default action.

4. **Progress override** — `decision_engine.py` can suppress sell/recycle for crafting-needed items. If an item is needed for an incomplete quest or hideout module, it may be silently kept. Check `ProgressSettings` to confirm quest/hideout state is current.

5. **Action enum identity** — `keep`, `sell`, `recycle` are compared as strings in some paths. Casing or trailing whitespace in a rule file will cause a mismatch that silently falls through to the default action.
