---
name: scan-report
description: Use when user wants to Summarize the last dry-run scan output from /tmp/scan-diag.txt and classify failures by type
---

Read and classify the most recent dry-run output:

```bash
cat /tmp/scan-diag.txt 2>/dev/null || echo "No scan-diag.txt found — run: uv run autoscrapper scan --dry-run 2>&1 | tee /tmp/scan-diag.txt"
```

Classify each outcome line:

| Outcome | Meaning | Fix path |
|---------|---------|---------|
| `SKIP_UNLISTED` | OCR read a name but no rule matched | Check rule store, fuzzy threshold, item name |
| `SKIP_EMPTY` | Slot appeared empty | Expected — verify count is reasonable for grid size |
| `UNAVAILABLE` | Context-menu OCR matched "Unavailable" button | Check `startswith("unavailable")` guard in `ocr_context_menu` |
| Action taken (`SELL`/`KEEP`/`RECYCLE`) | Rule matched and action dispatched | Verify correct rule won (custom vs default precedence) |
| `infobox not found` / timeout | Page detection failed | Route to `scan-validator` agent |
| Garbled item name | OCR misread | Route to `ocr-reviewer` agent |

Output a structured report:
1. **Outcome table** — counts per outcome type
2. **Top 3 issues** — most actionable failures with item name + outcome
3. **Suggested fix path** — which skill or agent to invoke next

Related skills: `/diagnose-scan`, `/ocr-debug`, `/scan-failed`
