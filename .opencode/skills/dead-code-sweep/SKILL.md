---

name: dead-code-sweep
description: Use when user wants to Find and remove genuine dead code using deadcode + vulture. Filters known false positives (dataclass fields, protocol methods, dunder hooks). Run before a cleanup commit.

# Dead Code Sweep

Finds unreferenced code using two complementary tools and removes confirmed dead code.

## Step 1 - Run scanners

```bash
uv run deadcode src/ 2>&1
uv run vulture src/ --min-confidence 80 2>&1
```

## Step 2 - Filter false positives

Before removing anything, verify each reported symbol is actually unused:

## Check all callers of a symbol

grep -rn "symbol_name" src/ tests/ scripts/

**Known false positive patterns - do NOT remove these:**

- Dataclass fields: `@dataclass` fields look like unused assignments but are accessed via `instance.field`
- `__slots__` entries: Accessed dynamically; scanners miss attribute access
- Protocol/ABC methods: Required by interface even if no direct call in this repo
- Textual `on_*` / `compose` / `action_*`: Called by framework via event dispatch
- `BENCHMARK_REPORTS_DIR`, `FIXED_FAILURE_CORPUS_PATH` etc.: Imported by scripts outside `src/`

**Verification workflow for each candidate:**

1. `grep -rn "ClassName\|method_name\|CONSTANT_NAME" src/ tests/ scripts/ .github/` - if any matches beyond definition, it's live
2. If a class: check if it's a dataclass (`@dataclass`), NamedTuple, or Protocol
3. If a function: check if it's registered as a Textual action or event handler

### Step 3 - Remove confirmed dead code

Only remove when grep confirms zero callers and the symbol has no interface obligation.

After removal, run:

uv run ruff check src/ tests/
uv run pytest --tb=short -q

Both must pass before committing.

### Step 4 - Commit

git add <changed files>
git commit -m "chore: remove dead code (<symbols removed>)"

### Notes from prior sweeps

- `RateLimitInfo` (`api/models.py`) - removed 2026-04-16; was a dataclass with zero callers
- `center_by_index` (`interaction/inventory_grid.py`) - removed 2026-04-16; only definition, no callers
- `deadcode` misses cross-module script usage (e.g., `update_report.py` functions called by `scripts/`) - always grep before removing
- `vulture` at `--min-confidence 80` still produces false positives for dataclass fields; verify before acting
