# Config Bump

Safely add, remove, or rename config fields.

**When:** Editing `@dataclass` fields in `src/autoscrapper/config.py`

**Current version:** `CONFIG_VERSION = 5`

**Steps:**

1. **Make your dataclass change** - add, remove, or rename the field with a sensible default

2. **Increment CONFIG_VERSION:**
   ```python
   CONFIG_VERSION = 6  # was 5
   ```

3. **Add a migration function** - find `_MIGRATIONS` dict in `config.py`:
   ```python
   def _migrate_v5_to_v6(payload: dict) -> None:
       payload.setdefault("my_new_field", False)
       if "old_name" in payload:
           payload["new_name"] = payload.pop("old_name")
       payload.pop("removed_field", None)

   _MIGRATIONS = {
       5: _migrate_v5_to_v6,
   }
   ```

4. **Validate:**
   ```bash
   uv run pytest tests/autoscrapper/test_config.py -v
   ```

5. **Verify loading from old config:**
   ```bash
   uv run autoscrapper scan --dry-run
   ```
   Check logs for migration confirmation.

**Checklist:**
- [ ] `CONFIG_VERSION` incremented
- [ ] Migration function added to `_MIGRATIONS`
- [ ] `pytest tests/autoscrapper/test_config.py` passes
- [ ] No field removed without `payload.pop("old_field", None)` in migration

**Related:** Skill: `config-bump` | Agent: `config-reviewer`
