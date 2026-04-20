---

name: config-bump
description: "Workflow for safely adding, removing, or renaming persisted config fields in config.py. Use whenever editing dataclass fields in src/autoscrapper/config.py. Covers incrementing CONFIG_VERSION, writing a migration function, and validating the round-trip."
disable-model-invocation: true

# Config Bump

Every time you add, remove, or rename a field in any `@dataclass` inside `src/autoscrapper/config.py`, you **must** bump `CONFIG_VERSION` and register a migration.

Without this, users' stored configs silently lose new fields on next load. The hook in `settings.json` fires a reminder on every edit to `config.py`.

## Current version

```bash
grep 'CONFIG_VERSION' src/autoscrapper/config.py
```

Currently `CONFIG_VERSION = 5`.

## Steps

### 1. Make your dataclass change

Add, remove, or rename the field. Set a sensible default using `field(default_factory=...)` or a plain default.

### 2. Increment CONFIG_VERSION

```python

# config.py
CONFIG_VERSION = 6 # was 5

### 3. Add a migration function
Find `_MIGRATIONS` dict in `config.py` (near line 114). Add an entry for the transition from old → new version:

def _migrate_v5_to_v6(payload: dict) -> None:
 # Example: add new field with default
 payload.setdefault("my_new_field", False)
 # Example: rename field
 if "old_name" in payload:
 payload["new_name"] = payload.pop("old_name")
 # Example: remove field
 payload.pop("removed_field", None)

_MIGRATIONS = {
 # ... existing entries ...
 5: _migrate_v5_to_v6,
}

Migration functions receive the raw `dict` payload and mutate it in place. They run in sequence (5→6, 6→7, etc.) so each should only handle one version transition.

### 4. Validate
uv run pytest tests/autoscrapper/test_config.py -v

The test suite covers round-trip serialization, version migration, and field clamping. All tests must pass.

### 5. Verify loading from old config
If you have a real config file at `%APPDATA%\autoscrapper\config.json` (Windows), confirm it loads without errors after the bump:

uv run autoscrapper scan --dry-run

Check logs for `"config: stored version X is older than current version Y; migrating automatically"` - that confirms migration ran.

## Checklist
- [ ] `CONFIG_VERSION` incremented
- [ ] Migration function added to `_MIGRATIONS` for the new transition
- [ ] `pytest tests/autoscrapper/test_config.py` passes
- [ ] No field removed without a `payload.pop("old_field", None)` in the migration
```
