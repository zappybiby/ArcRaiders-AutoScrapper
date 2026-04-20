---
name: add-rule
description: Use when user wants to Guided workflow for adding or editing a custom item rule in items_rules.json
disable-model-invocation: true
---

To add or change a rule for an item:

1. **Find the rules file:**
   ```bash
   # Default location (if no custom file configured):
   ls src/autoscrapper/items/items_rules.default.json
   # Custom file (set in settings — this takes precedence):
   # Check Settings → Rules File Path in the TUI
   ```

2. **Rule format:**
   ```json
   { "item_name": "Arc Alloy", "action": "sell" }
   ```
   Valid actions: `keep`, `sell`, `recycle`

3. **Do not edit `items_rules.default.json`** — it is overwritten by the update script. Add custom rules to your custom rules file (configured in Settings).

4. **Validate after adding:**
   ```bash
   uv run autoscrapper scan --dry-run
   ```
   Check logs for the item — confirm the correct action appears.
