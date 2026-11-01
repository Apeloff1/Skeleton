"""Regression: independent pins must be valid lowercase SHA-256, not literal \\Z suffixes.

These tests exercise the canonical batch admission path shared by publish,
resume, inspection, triage and the owner-private pinned job-file bridge.
"""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, FirstPlayableDeliveryBatchError, _PIN, _check_jobs, _parse_job,
)


def _jobs(root):
    return tuple(
        DeliveryJob(
            source=root / f"original-{index}",
            archive=root / f"game-{index}.zip",
            install=root / f"installed-{index}",
            save=root / f"save-{index}.json",
            receipt=root / f"receipt-{index}.json",
            manifest_sha256=str(index + 1) * 64,
            moves=("up", "right"),
            archive_sha256=str(index + 3) * 64,
            save_sha256=str(index + 5) * 64,
            receipt_sha256=str(index + 7) * 64,
        )
        for index in range(2)
    )


def test_valid_independent_pins_admitted_for_inspection_and_resume(tmp_path):
    jobs = _jobs(tmp_path)
    summary = tmp_path / "summary.json"
    assert _check_jobs(jobs, summary, inspect=True) == jobs
    assert _check_jobs(jobs, summary, inspect=None) == jobs
    assert _PIN.fullmatch("a" * 64) is not None


def test_valid_pins_are_not_publication_authority(tmp_path):
    with pytest.raises(FirstPlayableDeliveryBatchError, match="publication"):
        _check_jobs(_jobs(tmp_path), tmp_path / "summary.json", inspect=False)


@pytest.mark.parametrize("suffix", [r"\Z", "\n", " ", "0", "\x00"])
def test_trailing_bytes_cannot_be_accepted_as_digest(tmp_path, suffix):
    jobs = _jobs(tmp_path)
    modified = (replace(jobs[0], archive_sha256="a" * 64 + suffix), jobs[1])
    assert _PIN.fullmatch("a" * 64 + suffix) is None
    with pytest.raises(FirstPlayableDeliveryBatchError, match="lowercase SHA-256"):
        _check_jobs(modified, tmp_path / "summary.json", inspect=True)


@pytest.mark.parametrize("value", ["A" * 64, "g" * 64, "a" * 63, "", "a" * 65])
def test_noncanonical_digest_fails_closed(tmp_path, value):
    jobs = _jobs(tmp_path)
    modified = (replace(jobs[0], receipt_sha256=value), jobs[1])
    with pytest.raises(FirstPlayableDeliveryBatchError, match="lowercase SHA-256"):
        _check_jobs(modified, tmp_path / "summary.json", inspect=None)


def test_json_job_parser_and_canonical_admission_agree(tmp_path):
    job = _jobs(tmp_path)[0]
    raw = json.dumps({
        "source": str(job.source),
        "archive": str(job.archive),
        "install": str(job.install),
        "save": str(job.save),
        "receipt": str(job.receipt),
        "manifest_sha256": job.manifest_sha256,
        "moves": list(job.moves),
        "archive_sha256": job.archive_sha256,
        "save_sha256": job.save_sha256,
        "receipt_sha256": job.receipt_sha256,
    })
    parsed = _parse_job(raw)
    assert parsed.source == str(job.source)
    assert parsed.archive == str(job.archive)
    assert parsed.install == str(job.install)
    assert parsed.save == str(job.save)
    assert parsed.receipt == str(job.receipt)
    assert parsed.manifest_sha256 == job.manifest_sha256
    assert parsed.moves == job.moves
    assert parsed.archive_sha256 == job.archive_sha256
    assert parsed.save_sha256 == job.save_sha256
    assert parsed.receipt_sha256 == job.receipt_sha256
    assert _check_jobs((parsed, _jobs(tmp_path)[1]), tmp_path / "summary.json", inspect=True)[0] == parsed


def test_missing_pin_triple_remains_rejected_in_inspection(tmp_path):
    jobs = _jobs(tmp_path)
    modified = (replace(jobs[0], receipt_sha256=None), jobs[1])
    with pytest.raises(FirstPlayableDeliveryBatchError, match="independent game pins"):
        _check_jobs(modified, tmp_path / "summary.json", inspect=True)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="partial game pin"):
        _check_jobs(modified, tmp_path / "summary.json", inspect=None)


@pytest.mark.parametrize("value", [None, 1, [], "A" * 64, "0" * 63, "0" * 65])
def test_source_manifest_pin_is_validated_before_any_delivery_io(tmp_path, value):
    jobs = _jobs(tmp_path)
    modified = (replace(jobs[0], manifest_sha256=value), jobs[1])
    with pytest.raises(FirstPlayableDeliveryBatchError, match="source manifest"):
        _check_jobs(modified, tmp_path / "summary.json", inspect=False)


@pytest.mark.parametrize("value", [None, 1, [], object()])
def test_untyped_delivery_paths_rejected_at_admission(tmp_path, value):
    jobs = _jobs(tmp_path)
    modified = (replace(jobs[0], source=value), jobs[1])
    with pytest.raises(FirstPlayableDeliveryBatchError, match="paths must"):
        _check_jobs(modified, tmp_path / "summary.json", inspect=False)
