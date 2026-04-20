# Triage Failures

Analyze OCR failure corpus for systematic misread patterns.

**Command:**
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

    mismatches = [(s.get("raw_text",""), s.get("chosen_name","")) for s in samples if s.get("raw_text") != s.get("chosen_name")]
    counter = collections.Counter(mismatches).most_common(10)
    print("Top raw→chosen mismatches:")
    for (raw, chosen), count in counter:
        print(f" {count:3d}x {raw!r:40s} → {chosen!r}")

    no_match = [s.get("chosen_name","") for s in samples if not s.get("matched_name")]
    if no_match:
        top_no_match = collections.Counter(no_match).most_common(10)
        print("Items with no rule match (consider adding rules):")
        for name, count in top_no_match:
            print(f" {count:3d}x {name!r}")

    sources = collections.Counter(s.get("source","?") for s in samples)
    print(f"Source: {dict(sources)}")
EOF
```

**Interpreting output:**
- Same `raw_text` → wrong `chosen_name`: OCR preprocessing issue
- `matched_name` is null repeatedly: Item has no rule - use `/add-rule`
- High raw≠chosen count: Fuzzy threshold too low - check `score_cutoff`

**Next step:** Run `/ocr-corpus-replay` to validate threshold/preprocessing changes.

**Related:** Skills: `triage-failures`, `failure-to-fix` | Agent: `ocr-reviewer`
