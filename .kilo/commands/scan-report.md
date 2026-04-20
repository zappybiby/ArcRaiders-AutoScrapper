# Scan Report

Summarize the last dry-run scan output.

**Command:** `cat /tmp/scan-diag.txt 2>/dev/null || echo "Run: uv run autoscrapper scan --dry-run 2>&1 | tee /tmp/scan-diag.txt"`

**Classify each outcome:**
| Outcome | Meaning | Fix Path |
|---------|---------|----------|
| `SKIP_UNLISTED` | OCR read name but no rule matched | Check rule store, fuzzy threshold |
| `SKIP_EMPTY` | Slot empty | Expected - verify count |
| `UNAVAILABLE` | Context menu matched "Unavailable" button | Check `startswith("unavailable")` guard |
| Action taken | Rule matched | Verify rule precedence |
| `infobox not found` | Page detection failed | Route to `scan-validator` |
| Garbled text | OCR misread | Route to `ocr-reviewer` |

**Output format:**
1. **Outcome table** - counts per type
2. **Top 3 issues** - item name + outcome
3. **Suggested fix path** - which skill to invoke next

**Related:** Skills: `scan-report`, `scan-failed` | Command: `/diagnose-scan`
