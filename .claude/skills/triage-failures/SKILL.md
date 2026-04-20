---
name: triage-failures
description: Use when user wants to Analyze OCR failure corpus to find systematic misreads, top error patterns, and whether unlisted items need rules added
disable-model-invocation: true
---

Analyze the OCR failure corpus to surface systematic misread patterns:

```bash
uv run python - <<'EOF'
import orjson, collections
from pathlib import Path

REPO = Path(".")
files = {
    "captured": REPO / "artifacts/ocr/skip_unlisted/samples.jsonl",
    "fixed": REPO / "artifacts/ocr/failure_corpus.jsonl",
}

for label, path in files.items():
    if not path.exists():
        print(f"[{label}] not found: {path}")
        continue
    samples = [orjson.loads(l) for l in path.read_text().splitlines() if l.strip()]
    print(f"\n=== {label} ({len(samples)} samples) ===")
    if not samples:
        continue

    # Top raw→chosen mismatches
    mismatches = [(s.get("raw_text",""), s.get("chosen_name","")) for s in samples if s.get("raw_text") != s.get("chosen_name")]
    counter = collections.Counter(mismatches).most_common(10)
    print("Top raw→chosen mismatches:")
    for (raw, chosen), count in counter:
        print(f"  {count:3d}x  {raw!r:40s} → {chosen!r}")

    # Items with no match (matched_name is null)
    no_match = [s.get("chosen_name","") for s in samples if not s.get("matched_name")]
    if no_match:
        top_no_match = collections.Counter(no_match).most_common(10)
        print("Items with no rule match (consider adding rules):")
        for name, count in top_no_match:
            print(f"  {count:3d}x  {name!r}")

    # Source breakdown
    sources = collections.Counter(s.get("source","?") for s in samples)
    print(f"Source: {dict(sources)}")
EOF
```

**Interpreting the output:**

| Pattern | Action |
|---|---|
| Same `raw_text` maps to wrong `chosen_name` | OCR preprocessing issue — check binarization or upscale |
| `matched_name` is null repeatedly | Item has no rule — use `/add-rule` skill |
| Infobox vs context_menu skew | One detection path is degraded — run `/dry-run` to compare |
| High raw≠chosen count | Fuzzy threshold may be too low — check `score_cutoff` in `item_actions.py` |

After identifying patterns, run `/corpus-replay` to validate any threshold or preprocessing changes against the fixed corpus.
