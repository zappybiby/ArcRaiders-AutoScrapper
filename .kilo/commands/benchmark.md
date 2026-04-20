# Benchmark Tesseract

Benchmark tessdata model variants (fast vs best).

**Command:** `uv run python scripts/benchmark_tessdata_models.py`

**Review output for:**
- **Accuracy** - per-model match rate
- **Speed** - per-item timing (ms)
- **Recommendation** - best model for current threshold

**After benchmarking:**
1. Run OCR corpus replay to validate new model
2. Adjust `score_cutoff` if needed (see threshold-change)
3. Update model references in `src/autoscrapper/ocr/tesseract.py`
