---
name: benchmark
description: Use when user wants to Benchmark Tesseract tessdata model variants (fast vs best) for accuracy and speed tradeoffs
---

Run the Tesseract model benchmark against the current fixture corpus:

```bash
uv run python scripts/benchmark_tessdata_models.py
```

Review the output for:
- **Accuracy** — per-model match rate against known item names
- **Speed** — per-item timing (ms)
- **Recommendation** — which model to use given the current threshold

After benchmarking, if switching tessdata models:
1. Run `/corpus-replay` to validate the new model against all failure corpus samples
2. If `score_cutoff` needs adjustment, see `/threshold-change` before committing
3. Update any model references in `src/autoscrapper/ocr/tesseract.py`
