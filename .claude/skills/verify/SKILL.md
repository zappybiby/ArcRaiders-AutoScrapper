---
name: verify
description: Use when user wants to Run the full validation suite (lint + types + tests) before marking any code change done.
---

Run these commands in sequence from the project root. Stop and report on the first failure.

```bash
uv run ruff check src/ tests/
uv run basedpyright src/
uv run ty check src/
uv run pytest
```

**ty vs basedpyright disagreements**: If only `ty` reports an error and basedpyright is clean, check whether it's a known ty false positive before fixing (e.g., `dict[object, object]` key narrowing after `isinstance(value, dict)` — fix with `isinstance(key, str)` guard; `dict[Never, Never]` narrowing after type-narrowed isinstance — known ty limitation, suppress with `# type: ignore[union-attr]`).

Report: pass/fail per step, any errors inline. Do not claim the change is done until all four pass.
