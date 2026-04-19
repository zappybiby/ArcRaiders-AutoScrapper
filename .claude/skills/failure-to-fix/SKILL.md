---
name: failure-to-fix
description: Use when user wants to End-to-end scan failure pipeline — diagnose, identify root cause, fix, corpus replay, verify.
---

Use when a scan produces wrong actions, misread item names, or crashes. Chains diagnose → fix → validate without manual hand-offs.

## Step 1 — Capture dry-run output

```bash
uv run autoscrapper scan --dry-run 2>&1 | tee /tmp/scan-diag.txt
```

Debug images land in `ocr_debug/`. Key patterns:

| File | What to look for |
|---|---|
| `*_infobox_detect_overlay.png` | Green = detected, red = missed |
| `*_ctx_menu_processed.png` | Text should be sharp and readable |
| `*_infobox_action_*_processed.png` | Check binarization — text must be legible |

## Step 2 — Classify the failure

Read `/tmp/scan-diag.txt` and route:

| Symptom | Root cause | Next step |
|---|---|---|
| Garbled item names, low fuzzy score | OCR preprocessing / threshold | Step 3a |
| `infobox not found`, timeout, wrong page state | Geometry / detection | Step 3b |
| Wrong action (SELL when should KEEP), `SKIP_UNLISTED` | Rules | Step 3c |
| `CONFIG_VERSION`, deserialization error | Config schema | Step 3d |

Use `/triage-failures` first if the failure corpus has relevant samples.

## Step 3 — Fix

**3a — OCR / threshold issue**

- Dispatch `ocr-reviewer` agent with the log and relevant `ocr_debug/` image timestamps.
- If the fix changes `score_cutoff` or binarization thresholds, use `/threshold-change` for safe before/after corpus replay.
- Otherwise run `/ocr-corpus-replay` after the fix.

**3b — Geometry / detection issue**

- Dispatch `scan-validator` agent with the log and page-state transitions.
- Use `/calibrate-vision` if the context-menu crop constants need recalibration.

**3c — Rules issue**

- Dispatch `rules-reviewer` agent with the item names that got wrong actions.
- Use `/add-rule` to add or correct custom rules.
- No corpus replay needed — run verify directly (Step 4).

**3d — Config issue**

- Dispatch `config-reviewer` agent with the config diff.
- Use `/config-bump` to version-bump the schema change safely.

## Step 4 — Validate the fix

Re-run dry-run and confirm the original failure is gone:

```bash
uv run autoscrapper scan --dry-run 2>&1 | tail -30
```

Then run the full suite:

```bash
uv run ruff check src/ tests/
uv run basedpyright src/
uv run pytest
```

## Step 5 — Cleanup

```bash
# Prune ocr_debug/ images from this session (keep 1 day)
uv run autoscrapper clean-debug 1
```

Then use `/ci-promote` to push the fix.
