from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import orjson
import pytest

from autoscrapper.ocr.failure_corpus import (
    OcrFailureLabelStatus,
    CorpusPaths,
    OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
    OcrFailureSample,
    _coerce_sample,
    _iso_now,
    _sample_id,
    capture_skip_unlisted_sample,
    default_capture_paths,
    load_failure_corpus,
    resolve_image_path,
    write_report,
)


def test_iso_now() -> None:
    iso = _iso_now()
    assert iso.endswith("Z")
    # Should be parseable
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
    assert parsed.microsecond == 0


def test_sample_id_deterministic() -> None:
    id1 = _sample_id(
        raw_text="Test Name",
        chosen_name="Expected Name",
        source="infobox",
        image=None,
    )
    id2 = _sample_id(
        raw_text="Test Name",
        chosen_name="Expected Name",
        source="infobox",
        image=None,
    )
    assert id1 == id2


def test_sample_id_with_image() -> None:
    id1 = _sample_id(
        raw_text="Test",
        chosen_name="Expected",
        source="infobox",
        image=None,
    )
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    id2 = _sample_id(
        raw_text="Test",
        chosen_name="Expected",
        source="infobox",
        image=image,
    )
    assert id1 != id2


def test_coerce_sample_valid() -> None:
    valid_dict = {
        "schema_version": OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP",
        "source": "infobox",
        "raw_text": "raw",
        "cleaned_text": "clean",
        "chosen_name": "chosen",
        "matched_name": "match",
        "label_status": "match",
        "expected_name": "expect",
        "image_path": "path/img.webp",
        "threshold": 75,
    }
    sample = _coerce_sample(valid_dict)
    assert sample is not None
    assert isinstance(sample, OcrFailureSample)
    assert sample.schema_version == OCR_FAILURE_SAMPLE_SCHEMA_VERSION
    assert sample.sample_id == "123"
    assert sample.matched_name == "match"
    assert sample.label_status == "match"
    assert sample.expected_match_status == "match"
    assert sample.is_authoritative is True
    assert sample.expected_display == "expect"
    assert sample.threshold == 75


def test_coerce_sample_invalid() -> None:
    assert _coerce_sample(None) is None
    assert _coerce_sample([]) is None

    # Missing required string
    invalid_dict = {
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP",
        "source": "infobox",
        "raw_text": "raw",
        "cleaned_text": "clean",
        # missing chosen_name
    }
    assert _coerce_sample(invalid_dict) is None

    # Invalid source
    invalid_source = {
        "schema_version": OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP",
        "source": "invalid",
        "raw_text": "raw",
        "cleaned_text": "clean",
        "chosen_name": "chosen",
    }
    assert _coerce_sample(invalid_source) is None


def test_coerce_sample_defaults_old_unlabeled_rows_to_pending() -> None:
    sample = _coerce_sample({
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP_UNLISTED",
        "source": "infobox",
        "raw_text": "raw",
        "cleaned_text": "clean",
        "chosen_name": "chosen",
        "matched_name": None,
    })
    assert sample is not None
    assert sample.schema_version == 1
    assert sample.label_status == "pending"
    assert sample.expected_match_status is None
    assert sample.expected_display == "<pending-label>"


def test_coerce_sample_infers_match_label_for_old_fixed_corpus_rows() -> None:
    sample = _coerce_sample({
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP_UNLISTED",
        "source": "infobox",
        "raw_text": "raw",
        "cleaned_text": "clean",
        "chosen_name": "chosen",
        "matched_name": "Arc Alloy",
        "expected_name": "Arc Alloy",
    })
    assert sample is not None
    assert sample.label_status == "match"
    assert sample.expected_match_status == "match"
    assert sample.expected_display == "Arc Alloy"


def test_coerce_sample_no_match_label_is_authoritative() -> None:
    sample = _coerce_sample({
        "schema_version": OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP_UNLISTED",
        "source": "context_menu",
        "raw_text": "Unavailable",
        "cleaned_text": "Unavailable",
        "chosen_name": "Unavailable",
        "matched_name": None,
        "label_status": "no_match",
    })
    assert sample is not None
    assert sample.is_authoritative is True
    assert sample.expected_match_status == "no_match"
    assert sample.expected_display == "<no-match>"


def test_coerce_sample_rejects_match_label_without_expected_name() -> None:
    sample = _coerce_sample({
        "schema_version": OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP_UNLISTED",
        "source": "context_menu",
        "raw_text": "Arc Alloy",
        "cleaned_text": "Arc Alloy",
        "chosen_name": "Arc Alloy",
        "matched_name": "Arc Alloy",
        "label_status": "match",
    })
    assert sample is None


def test_capture_skip_unlisted_sample(tmp_path: Path) -> None:
    manifest_path = tmp_path / "samples.jsonl"
    images_dir = tmp_path / "images"
    paths = CorpusPaths(manifest_path=manifest_path, images_dir=images_dir)

    with patch("autoscrapper.ocr.failure_corpus.REPO_ROOT", tmp_path):
        image = np.zeros((10, 10, 3), dtype=np.uint8)

        sample = capture_skip_unlisted_sample(
            raw_text="Raw Text \n",
            chosen_name="Chosen Name",
            matched_name="Matched",
            source_image=image,
            from_context_menu=True,
            threshold=75,
            paths=paths,
        )

        assert sample is not None
        assert sample.schema_version == OCR_FAILURE_SAMPLE_SCHEMA_VERSION
        assert sample.source == "context_menu"
        assert sample.raw_text == "Raw Text"  # stripped
        assert sample.cleaned_text == "Raw Text"
        assert sample.label_status == "pending"
        assert sample.expected_display == "<pending-label>"
        assert sample.threshold == 75

        assert manifest_path.exists()
        content = manifest_path.read_text("utf-8").strip()
        assert len(content.split("\n")) == 1

        data = orjson.loads(content)
        assert data["schema_version"] == OCR_FAILURE_SAMPLE_SCHEMA_VERSION
        assert data["sample_id"] == sample.sample_id
        assert data["source"] == "context_menu"
        assert data["label_status"] == "pending"
        assert data["threshold"] == 75

        assert images_dir.exists()
        images = list(images_dir.glob("*.webp"))
        assert len(images) == 1
        assert sample.image_path is not None
        assert str(sample.image_path).endswith(f"{sample.sample_id}.webp")


def test_capture_skip_unlisted_sample_empty_text(tmp_path: Path) -> None:
    paths = CorpusPaths(manifest_path=tmp_path / "samples.jsonl", images_dir=tmp_path / "images")

    sample = capture_skip_unlisted_sample(
        raw_text="  \n ",  # empty when cleaned
        chosen_name="Fallback Name",
        matched_name=None,
        source_image=None,
        from_context_menu=False,
        threshold=70,
        paths=paths,
    )

    assert sample is not None
    assert sample.cleaned_text == "Fallback Name"
    assert sample.raw_text == "Fallback Name"  # sample_raw_text is empty, so it uses cleaned_text
    assert sample.threshold == 70


def test_capture_skip_unlisted_sample_completely_empty(tmp_path: Path) -> None:
    paths = CorpusPaths(manifest_path=tmp_path / "samples.jsonl", images_dir=tmp_path / "images")

    sample = capture_skip_unlisted_sample(
        raw_text="  \n ",
        chosen_name="   ",  # also empty
        matched_name=None,
        source_image=None,
        from_context_menu=False,
        paths=paths,
    )

    assert sample is None


def test_load_failure_corpus(tmp_path: Path) -> None:
    manifest_path = tmp_path / "samples.jsonl"

    assert load_failure_corpus(manifest_path) == []

    valid_dict = {
        "schema_version": OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        "sample_id": "123",
        "captured_at": "2023-01-01T00:00:00Z",
        "outcome": "SKIP",
        "source": "infobox",
        "raw_text": "raw",
        "cleaned_text": "clean",
        "chosen_name": "chosen",
    }

    with manifest_path.open("wb") as f:
        f.write(orjson.dumps(valid_dict) + b"\n")
        f.write(b"  \n")  # empty line
        f.write(b'{"invalid": "json"\n')  # this line doesn't throw, we handle it below
        f.write(orjson.dumps({"valid": "json_but_invalid_sample"}) + b"\n")  # coerce returns None

    # Load failure corpus will throw if json isn't well formed per line,
    # instead of crashing let's just make sure load failure corpus handles what it's supposed to

    # Write a new manifest for clean load
    manifest_path2 = tmp_path / "samples2.jsonl"
    with manifest_path2.open("wb") as f:
        f.write(orjson.dumps(valid_dict) + b"\n")
        f.write(orjson.dumps({"valid": "json_but_invalid_sample"}) + b"\n")  # coerce returns None
        f.write(b"  \n")
        f.write(b"\n")

    samples = load_failure_corpus(manifest_path2)
    assert len(samples) == 1
    assert samples[0].sample_id == "123"

    # Also check if we can catch the exception for invalid JSON
    with pytest.raises(orjson.JSONDecodeError):
        load_failure_corpus(manifest_path)


def test_resolve_image_path(tmp_path: Path) -> None:
    sample = OcrFailureSample(
        schema_version=OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        sample_id="123",
        captured_at="now",
        outcome="SKIP",
        source="infobox",
        raw_text="raw",
        cleaned_text="clean",
        chosen_name="chosen",
        matched_name=None,
        image_path=None,
    )
    assert resolve_image_path(sample, manifest_path=tmp_path / "manifest.jsonl") is None

    abs_path = tmp_path / "img.webp"
    sample_abs = OcrFailureSample(
        schema_version=OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        sample_id="123",
        captured_at="now",
        outcome="SKIP",
        source="infobox",
        raw_text="raw",
        cleaned_text="clean",
        chosen_name="chosen",
        matched_name=None,
        image_path=str(abs_path),
    )
    assert resolve_image_path(sample_abs, manifest_path=tmp_path / "manifest.jsonl") == abs_path

    # Relative to manifest
    sample_rel = OcrFailureSample(
        schema_version=OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        sample_id="123",
        captured_at="now",
        outcome="SKIP",
        source="infobox",
        raw_text="raw",
        cleaned_text="clean",
        chosen_name="chosen",
        matched_name=None,
        image_path="images/img.webp",
    )
    manifest_dir = tmp_path / "corpus"
    manifest_path = manifest_dir / "manifest.jsonl"
    resolved = resolve_image_path(sample_rel, manifest_path=manifest_path)
    assert resolved == manifest_dir / "images/img.webp"


def test_write_report(tmp_path: Path) -> None:
    payload = {"status": "ok"}
    report_dir = tmp_path / "reports"

    path = write_report(report_dir, "test_prefix", payload)

    assert path.exists()
    assert report_dir.exists()
    assert path.name.startswith("test_prefix_")
    assert path.name.endswith(".json")

    content = json.loads(path.read_text("utf-8"))
    assert content == payload


def test_default_capture_paths() -> None:
    paths = default_capture_paths()
    assert isinstance(paths, CorpusPaths)
    assert isinstance(paths.manifest_path, Path)
    assert isinstance(paths.images_dir, Path)


def test_resolve_image_path_traversal(tmp_path: Path) -> None:
    sample = OcrFailureSample(
        schema_version=2,
        sample_id="123",
        captured_at="now",
        outcome="SKIP",
        source="infobox",
        raw_text="raw",
        cleaned_text="clean",
        chosen_name="chosen",
        matched_name=None,
        image_path="../../etc/passwd",
    )

    # Using tmp_path as REPO_ROOT via patch
    with patch("autoscrapper.ocr.failure_corpus.REPO_ROOT", tmp_path.resolve()):
        manifest_path = tmp_path / "corpus" / "manifest.jsonl"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        resolved = resolve_image_path(sample, manifest_path=manifest_path)
        assert resolved is None


@pytest.mark.parametrize(
    ("label_status", "expected"),
    [
        ("match", True),
        ("no_match", True),
        ("pending", False),
        ("ambiguous", False),
    ],
)
def test_ocr_failure_sample_is_authoritative(label_status: OcrFailureLabelStatus, expected: bool) -> None:
    sample = OcrFailureSample(
        schema_version=OCR_FAILURE_SAMPLE_SCHEMA_VERSION,
        sample_id="123",
        captured_at="2023-01-01T00:00:00Z",
        outcome="SKIP",
        source="infobox",
        raw_text="raw",
        cleaned_text="clean",
        chosen_name="chosen",
        matched_name=None,
        label_status=label_status,
    )
    assert sample.is_authoritative is expected
