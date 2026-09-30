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
VERIFIER_HEAD = "2951c036fbe297dabc19f9021c008d6b69b7b5fe"
VERIFIER_RUN_ID = 36766395171
VERIFIER_JOB_ID = 110061859992
ENVIRONMENT_MANIFEST_DIGEST = "6aa7bce943d27979295bbb754f4c6f8c07809eab6cea9ad034c5b310db9f4c10"
BOUND_AT = "2026-09-30T19:40:00Z"
REVIEW_AT = "2026-10-30T19:40:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "hermetic_build": "2d6af66d7de19fe59ecdbeb530417c32f7b8f3898fabf3c03ecc789b52ec2e7c",
    "environment_replay": "7e9ef4b551d9aab65a18002220b95cd9500947441228d32617de541749a200cc",
    "cross_environment_reproduction": "ada856cd69b83dbb4d8cae575b69dc0bb4ba59d690b552fa2282293a096f4a2f",
    "dependency_lock_check": "253686df4a0c6833bcb5ae45643376a1b696470edcd23cd43a895301e94ab3a9",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _binding() -> dict:
    registry = _load(ROOT / REGISTRY)
    rows = [
        row
        for row in registry["records"]
        if row["obligation_id"] == OBLIGATION_ID
    ]
    assert len(rows) == 1
    return rows[0]


def _obligation():
    items = derive_obligations(
        _load(ROOT / MASTER),
        _load(ROOT / P1_MAP),
        _load(ROOT / ADVERSARIAL),
        _load(ROOT / POLICY),
    )
    rows = [
        item
        for item in items
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    assert len(rows) == 1
    return rows[0]


def test_ac22_binding_pins_successful_cross_environment_verifier() -> None:
    row = _binding()

    assert VERIFIER_RUN_ID == 36766395171
    assert VERIFIER_JOB_ID == 110061859992
    assert len(ENVIRONMENT_MANIFEST_DIGEST) == 64
    assert row["obligation_id"] == OBLIGATION_ID
    assert row["obligation_digest"] == OBLIGATION_DIGEST
    assert row["owner_id"] == OWNER_ID
    assert row["severity"] == "high"
    assert row["disposition"] == "evidence"
    assert row["bound_at"] == BOUND_AT
    assert row["review_at"] == REVIEW_AT
    assert row["accepted_risk"] is None

    by_category = {item["category"]: item for item in row["evidence"]}
    assert set(by_category) == set(EXPECTED)
    for category, digest in EXPECTED.items():
        evidence = by_category[category]
        assert evidence["digest"] == digest
        assert evidence["source"] == (
            f"p1:adversarial-ac22-evidence:{AXIS_ID}:"
            f"{category}:{VERIFIER_HEAD}"
        )


def test_ac22_binding_matches_live_canonical_obligation() -> None:
    obligation = _obligation()

    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED)


def test_ac22_binding_advances_frontier_without_risk_acceptance() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 497
    assert report["resolved_count"] == 497
    assert report["unresolved_blocking_count"] == 16
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 497,
        "unbound": 16,
    }
