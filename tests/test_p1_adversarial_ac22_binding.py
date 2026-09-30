from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.reconcile_p1_risk_evidence import (
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
    reconcile_repository,
)

AXIS_ID = "AC-22"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-22-0debb8ba51d7d7f2"
OBLIGATION_DIGEST = "c62c08156de317799383d67f24efc9a9e4ed1932b5a255005f2708b2672271bd"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "4d1788b2af39a63f2b12208164ab9a8f0cfdd5c7"
VERIFIER_RUN_ID = 36766424402
VERIFIER_JOB_ID = 110062146872
ENVIRONMENT_MANIFEST_DIGEST = "6aa7bce943d27979295bbb754f4c6f8c07809eab6cea9ad034c5b310db9f4c10"
BOUND_AT = "2026-09-30T19:35:00Z"
REVIEW_AT = "2026-10-30T19:35:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED_EVIDENCE = {
    "hermetic_build": "022e33caf462d06e39ca8d0af7f5c2a681f63e40528c180c48c0050048cb20a8",
    "environment_replay": "8f671c349c9a8f75825da825d2c1d077f6ac5e453d27a49fc9510075e157a499",
    "cross_environment_reproduction": "0635eaa0fef096a53f187a300d447dcbbc73fdfb01d1d8f50c3ccb19b72db7ee",
    "dependency_lock_check": "051aa587d9b75e3ac93e96e2b2c7ba54b3a114c758732fcda3c8023a460c4670",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _obligations():
    return derive_obligations(
        _load(ROOT / MASTER),
        _load(ROOT / P1_MAP),
        _load(ROOT / ADVERSARIAL),
        _load(ROOT / POLICY),
    )


def _binding() -> dict:
    registry = _load(ROOT / REGISTRY)
    matches = [
        row
        for row in registry["records"]
        if row["obligation_id"] == OBLIGATION_ID
    ]
    assert len(matches) == 1
    return matches[0]


def test_ac22_binding_pins_successful_cross_environment_verifier() -> None:
    row = _binding()

    assert VERIFIER_RUN_ID == 36766424402
    assert VERIFIER_JOB_ID == 110062146872
    assert len(ENVIRONMENT_MANIFEST_DIGEST) == 64
    assert row["obligation_digest"] == OBLIGATION_DIGEST
    assert row["owner_id"] == OWNER_ID
    assert row["severity"] == "high"
    assert row["disposition"] == "evidence"
    assert row["bound_at"] == BOUND_AT
    assert row["review_at"] == REVIEW_AT
    assert row["accepted_risk"] is None

    by_category = {item["category"]: item for item in row["evidence"]}
    assert set(by_category) == set(EXPECTED_EVIDENCE)
    for category, digest in EXPECTED_EVIDENCE.items():
        evidence = by_category[category]
        assert evidence["digest"] == digest
        assert evidence["source"] == (
            f"p1:adversarial-ac22-evidence:{AXIS_ID}:"
            f"{category}:{VERIFIER_HEAD}"
        )


def test_ac22_binding_matches_live_adversarial_obligation() -> None:
    matches = [
        item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    assert len(matches) == 1
    obligation = matches[0]

    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED_EVIDENCE)


def test_ac22_binding_advances_frontier_without_risk_acceptance() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 495
    assert report["resolved_count"] == 495
    assert report["unresolved_blocking_count"] == 18
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 495,
        "unbound": 18,
    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [
        item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL
        and item.obligation_id not in bound
    ]
    assert len(unbound) == 18
    assert AXIS_ID not in {item.source_ref for item in unbound}
