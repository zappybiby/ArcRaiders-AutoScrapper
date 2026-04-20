---

name: scan-report
description: Use when user wants to Summarize the last dry-run scan output from /tmp/scan-diag.txt and classify failures by type

Read and classify the most recent dry-run output:

```bash
cat /tmp/scan-diag.txt 2>/dev/null || echo "No scan-diag.txt found - run: uv run autoscrapper scan --dry-run 2>&1 | tee /tmp/scan-diag.txt"
```

Classify each outcome line:

`SKIP_UNLISTED`, Meaning=OCR read a name but no rule matched, Fix path=Check rule store, fuzzy threshold, item name
`SKIP_EMPTY`, Meaning=Slot appeared empty, Fix path=Expected - verify count is reasonable for grid size
`UNAVAILABLE`, Meaning=Context-menu OCR matched "Unavailable" button, Fix path=Check `startswith("unavailable")` guard in `ocr_context_menu`
Action taken (`SELL`/`KEEP`/`RECYCLE`), Meaning=Rule matched and action dispatched, Fix path=Verify correct rule won (custom vs default precedence)
`infobox not found` / timeout, Meaning=Page detection failed, Fix path=Route to `scan-validator` agent
Garbled item name, Meaning=OCR misread, Fix path=Route to `ocr-reviewer` agent

Output a structured report:

1. **Outcome table** - counts per outcome type
2. **Top 3 issues** - most actionable failures with item name + outcome
3. **Suggested fix path** - which skill or agent to invoke next

Related skills: `/diagnose-scan`, `/ocr-debug`, `/scan-failed`
