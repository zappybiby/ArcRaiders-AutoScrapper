# Add Rule

Add or edit a custom item rule.

**Rule format:**
```json
{ "item_name": "Arc Alloy", "action": "sell" }
```
Valid actions: `keep`, `sell`, `recycle`

**Steps:**
1. **Find your rules file:**
   - Default: `src/autoscrapper/items/items_rules.default.json`
   - Custom (takes precedence): Set in Settings → Rules File Path in TUI

2. **Add your rule** to the custom rules file (not `items_rules.default.json` - it is overwritten by the update script)

3. **Validate:**
   ```bash
   uv run autoscrapper scan --dry-run
   ```
   Check logs for the item - confirm correct action appears.

**Tip:** Custom rules override bundled defaults. The merge order in `item_actions.py` must ensure custom > default.

**Related:** Skill: `add-rule` | Agent: `rules-reviewer`
