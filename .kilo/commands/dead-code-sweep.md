# Dead Code Sweep

Find and remove unreferenced code.

**Commands:**
```bash
uv run deadcode src/ 2>&1
uv run vulture src/ --min-confidence 80 2>&1
```

**Verify before removing:**
```bash
grep -rn "symbol_name" src/ tests/ scripts/
```

**Known false positives (do NOT remove):**
- Dataclass fields
- `__slots__` entries
- Protocol/ABC methods
- Textual `on_*` / `compose` / `action_*` handlers

**After removal:**
```bash
uv run ruff check src/ tests/
uv run pytest --tb=short -q
```
