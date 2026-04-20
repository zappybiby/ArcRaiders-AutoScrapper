# Verify Changes

Run the full validation suite (lint + types + tests).

**Commands:**
```bash
uv run ruff check src/ tests/
uv run basedpyright src/
uv run ty check src/
uv run pytest
```

**Usage:** Run before marking any code change complete. All four must pass.

**Note:** If only `ty` reports an error and basedpyright is clean, check for known ty false positives before fixing.
