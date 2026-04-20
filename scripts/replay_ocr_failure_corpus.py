from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autoscrapper.ocr.failure_corpus import (  # noqa: E402
    CAPTURED_MANIFEST_PATH,
    REPLAY_REPORTS_DIR,
    OcrFailureSample,
    load_failure_corpus,
    write_report,
)
from autoscrapper.ocr.inventory_vision import (  # noqa: E402
    DEFAULT_ITEM_NAME_MATCH_THRESHOLD,
    match_item_name_result,
)

SELECTION_POLICY = (
    "Prefer the current threshold when it passes; otherwise fall back to the lowest passing candidate threshold."
)
CANDIDATE_THRESHOLD_OFFSETS = (-10, -5, 0, 5, 10)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Replay captured SKIP_UNLISTED OCR samples against candidate fuzzy thresholds.")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=CAPTURED_MANIFEST_PATH,
        help="JSONL corpus to replay (default: %(default)s)",
    )
    parser.add_argument(
        "--threshold",
        dest="thresholds",
        action="append",
        type=int,
        help="Candidate threshold to evaluate; repeat to test multiple values.",
    )
    return parser


def _default_thresholds() -> list[int]:
    current = DEFAULT_ITEM_NAME_MATCH_THRESHOLD
    return sorted({
        value for value in (current + offset for offset in CANDIDATE_THRESHOLD_OFFSETS) if 0 <= value <= 100
    })


def _authoritative_samples(samples: list[OcrFailureSample]) -> list[OcrFailureSample]:
    return [sample for sample in samples if sample.is_authoritative]


def _evaluate_threshold(samples: list[OcrFailureSample], threshold: int) -> dict[str, object]:
    sample_reports: list[dict[str, object]] = []
    correct_count = 0
    for sample in samples:
        result = match_item_name_result(sample.raw_text, threshold)
        expects_no_match = sample.expected_match_status == "no_match"
        is_correct = (expects_no_match and result.matched_name is None) or result.matched_name == sample.expected_name
        if is_correct:
            correct_count += 1
        sample_reports.append({
            "sample_id": sample.sample_id,
            "source": sample.source,
            "raw_text": sample.raw_text,
            "cleaned_text": result.cleaned_text,
            "captured_cleaned_text": sample.cleaned_text,
            "label_status": sample.label_status,
            "expected_status": sample.expected_match_status,
            "expected": sample.expected_display,
            "match_status": "matched" if result.matched_name is not None else "no_match",
            "chosen_name": result.chosen_name,
            "matched_name": result.matched_name,
            "correct": is_correct,
        })

    sample_count = len(samples)
    passes = sample_count > 0 and correct_count == sample_count
    return {
        "threshold": threshold,
        "passes": passes,
        "correct_count": correct_count,
        "sample_count": sample_count,
        "samples": sample_reports,
    }


def _select_threshold(passing_thresholds: list[int]) -> int | None:
    if DEFAULT_ITEM_NAME_MATCH_THRESHOLD in passing_thresholds:
        return DEFAULT_ITEM_NAME_MATCH_THRESHOLD
    return passing_thresholds[0] if passing_thresholds else None


def main() -> int:
    args = _build_parser().parse_args()
    manifest_path = args.manifest.resolve()
    thresholds = sorted(set(args.thresholds or _default_thresholds()))
    samples = load_failure_corpus(manifest_path)
    authoritative_samples = _authoritative_samples(samples)

    threshold_reports: list[dict[str, object]] = []
    passing_thresholds: list[int] = []
    for threshold in thresholds:
        threshold_report = _evaluate_threshold(authoritative_samples, threshold)
        if threshold_report["passes"]:
            passing_thresholds.append(threshold)
        threshold_reports.append(threshold_report)

    selected_threshold = _select_threshold(passing_thresholds)
    report = {
        "manifest_path": manifest_path.as_posix(),
        "sample_count": len(samples),
        "authoritative_sample_count": len(authoritative_samples),
        "ignored_sample_count": len(samples) - len(authoritative_samples),
        "current_threshold": DEFAULT_ITEM_NAME_MATCH_THRESHOLD,
        "candidate_thresholds": thresholds,
        "selection_policy": SELECTION_POLICY,
        "passing_thresholds": passing_thresholds,
        "selected_threshold": selected_threshold,
        "threshold_reports": threshold_reports,
    }
    report_path = write_report(REPLAY_REPORTS_DIR, "ocr_threshold_replay", report)

    print(
        "samples={sample_count} authoritative={authoritative_sample_count} "
        "ignored={ignored_sample_count} manifest={manifest_path}".format(**report)
    )
    for threshold_report in threshold_reports:
        print("threshold={threshold} passes={passes} correct={correct_count}/{sample_count}".format(**threshold_report))
    print(f"report={report_path}")
    if not samples:
        print("No samples found; capture live SKIP_UNLISTED data before calibrating the threshold.")
    elif not authoritative_samples:
        print(
            "No authoritative labels found; mark samples with label_status=match|no_match before calibrating the threshold."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
