from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import orjson

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autoscrapper.ocr.failure_corpus import (  # noqa: E402
    BENCHMARK_REPORTS_DIR,
    FIXED_FAILURE_CORPUS_PATH,
    load_failure_corpus,
    resolve_image_path,
    write_report,
)
from autoscrapper.ocr.inventory_vision import (  # noqa: E402
    ocr_context_menu,
    ocr_title_strip,
)
from autoscrapper.ocr.tesseract import initialize_ocr  # noqa: E402

MODEL_PACKAGES = {
    "fast-eng": "tessdata.fast-eng",
    "best-eng": "tessdata.best-eng",
}
SELECTION_POLICY = (
    "Prefer best-eng only when it strictly improves corpus accuracy; ties keep "
    "fast-eng and elapsed time is reported for reference."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark tessdata.fast-eng vs tessdata.best-eng on a fixed OCR corpus."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=FIXED_FAILURE_CORPUS_PATH,
        help="JSONL corpus with authoritative match labels, image_path, and expected_name fields (default: %(default)s)",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--label",
        choices=sorted(MODEL_PACKAGES),
        help=argparse.SUPPRESS,
    )
    return parser


def _load_benchmark_samples(manifest_path: Path) -> list[tuple[object, Path]]:
    samples = []
    for sample in load_failure_corpus(manifest_path):
        if sample.expected_match_status != "match" or not sample.expected_name:
            continue
        image_path = resolve_image_path(sample, manifest_path=manifest_path)
        if image_path is None or not image_path.exists():
            continue
        samples.append((sample, image_path))
    return samples


def _run_worker(manifest_path: Path, label: str) -> dict[str, object]:
    backend = initialize_ocr()
    benchmark_samples = _load_benchmark_samples(manifest_path)

    sample_reports: list[dict[str, object]] = []
    correct_count = 0
    total_duration = 0.0
    for sample, image_path in benchmark_samples:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        sample_start = time.perf_counter()
        result = ocr_context_menu(image) if sample.source == "context_menu" else ocr_title_strip(image)
        elapsed = time.perf_counter() - sample_start
        total_duration += elapsed
        is_correct = result.item_name == sample.expected_name
        if is_correct:
            correct_count += 1
        sample_reports.append({
            "sample_id": sample.sample_id,
            "image_path": image_path.as_posix(),
            "expected_name": sample.expected_name,
            "recognized_name": result.item_name,
            "raw_item_text": result.raw_item_text,
            "correct": is_correct,
            "elapsed_seconds": elapsed,
        })

    sample_count = len(sample_reports)
    accuracy = (correct_count / sample_count) if sample_count else 0.0
    return {
        "label": label,
        "manifest_path": manifest_path.as_posix(),
        "sample_count": sample_count,
        "correct_count": correct_count,
        "accuracy": accuracy,
        "elapsed_seconds": total_duration,
        "backend": {
            "tesseract_version": backend.tesseract_version,
            "tessdata_dir": backend.tessdata_dir,
            "languages": backend.languages,
        },
        "samples": sample_reports,
    }


def _install_tessdata_package(package_name: str, target_dir: Path) -> str:
    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if pip_check.returncode != 0:
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            check=True,
            capture_output=True,
            text=True,
        )
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-deps",
        "--target",
        str(target_dir),
        package_name,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Could not install {package_name} for benchmarking: {detail}") from exc
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (f"import sys; sys.path.insert(0, {str(target_dir)!r}); import tessdata; print(tessdata.data_path())"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"Could not resolve tessdata dir for {package_name}")
    return lines[-1]


def _resolve_current_tessdata_dir() -> str:
    completed = subprocess.run(
        [sys.executable, "-c", "import tessdata; print(tessdata.data_path())"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Could not resolve the current tessdata dir")
    return lines[-1]


def _invoke_worker(manifest_path: Path, label: str, tessdata_dir: str) -> dict[str, object]:
    env = os.environ.copy()
    env["TESSDATA_PREFIX"] = tessdata_dir
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--label",
            label,
            "--manifest",
            str(manifest_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return orjson.loads(completed.stdout)


def main() -> int:
    args = _build_parser().parse_args()
    manifest_path = args.manifest.resolve()

    if args.worker:
        if not args.label:
            raise SystemExit("--label is required with --worker")
        sys.stdout.buffer.write(orjson.dumps(_run_worker(manifest_path, args.label)))
        sys.stdout.buffer.write(b"\n")
        return 0

    runs = []
    for label, package_name in MODEL_PACKAGES.items():
        try:
            if label == "fast-eng":
                tessdata_dir = _resolve_current_tessdata_dir()
            else:
                with TemporaryDirectory() as temp_dir_raw:
                    temp_dir = Path(temp_dir_raw)
                    tessdata_dir = _install_tessdata_package(package_name, temp_dir)

            run_report = _invoke_worker(manifest_path, label, tessdata_dir)
            run_report["package_name"] = package_name
            runs.append(run_report)
        except Exception as exc:
            runs.append({
                "label": label,
                "package_name": package_name,
                "sample_count": 0,
                "correct_count": 0,
                "accuracy": 0.0,
                "elapsed_seconds": 0.0,
                "backend": {
                    "tesseract_version": "",
                    "tessdata_dir": None,
                    "languages": [],
                },
                "samples": [],
                "error": str(exc),
            })

    fast_report = next(
        (report for report in runs if report["label"] == "fast-eng"),
        None,
    )
    best_report = next(
        (report for report in runs if report["label"] == "best-eng"),
        None,
    )
    if fast_report is None or best_report is None:
        raise RuntimeError("Benchmark did not produce both fast-eng and best-eng reports")
    selected_model = "best-eng" if best_report["accuracy"] > fast_report["accuracy"] else "fast-eng"
    report = {
        "manifest_path": manifest_path.as_posix(),
        "sample_count": fast_report["sample_count"],
        "selected_model": selected_model,
        "selection_policy": SELECTION_POLICY,
        "dependency_should_change": selected_model != "fast-eng",
        "runs": runs,
    }
    report_path = write_report(BENCHMARK_REPORTS_DIR, "tessdata_benchmark", report)

    for run_report in runs:
        if run_report.get("error"):
            print(
                "model={label} error={error}".format(
                    label=run_report["label"],
                    error=run_report["error"],
                )
            )
            continue
        print(
            "model={label} accuracy={accuracy:.3f} correct={correct_count}/{sample_count} elapsed={elapsed_seconds:.3f}s tessdata_dir={tessdata_dir}".format(
                **run_report,
                tessdata_dir=run_report["backend"]["tessdata_dir"],
            )
        )
    print(f"selected_model={selected_model}")
    print(f"report={report_path}")
    if fast_report["sample_count"] == 0:
        print(
            "No authoritative matched failure corpus entries were found; create a fixed corpus with label_status=match, image_path, and expected_name before benchmarking."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
