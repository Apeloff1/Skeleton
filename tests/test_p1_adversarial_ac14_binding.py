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

AXIS_ID = "AC-14"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-14-683997be530ee235"
OBLIGATION_DIGEST = "7d16b5bb575617c25697d08244e38700e55f5b431058c11ca6e7f7d9ceea0810"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "c255977275689aacdb8b7e2bb7764034da56dc30"
VERIFIER_RUN_ID = 36760238991
VERIFIER_JOB_ID = 110040647258
BOUND_AT = "2026-09-30T18:55:00Z"
REVIEW_AT = "2026-10-30T18:55:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED_EVIDENCE = {
    "evidence_digest_check": "7639f2acccbf381f7aecd706ccc17195861c7dd155449b305053273ddbc87e1f",
    "independent_verification": "734abba56e727e08ea7995f162df031497ae386bb648cbfcbb86db4d64f4735d",
    "failed_run_retention": "8b17217cc58bd9f747a17c042fe9ffdc3c1f1943f7a0faafa6f8e53de17c4dc0",
    "provenance_replay": "8b47706a2c7068bb39247e1694acecf55f170b2981291aca2925c475f78c6ae0",
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


def test_ac14_binding_pins_successful_exact_head_verifier() -> None:
    row = _binding()

    assert VERIFIER_RUN_ID == 36760238991
    assert VERIFIER_JOB_ID == 110040647258
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
            f"p1:adversarial-ac14-evidence:{AXIS_ID}:"
            f"{category}:{VERIFIER_HEAD}"
        )


def test_ac14_binding_matches_live_adversarial_obligation() -> None:
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


def test_ac14_binding_advances_frontier_without_risk_acceptance() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 509
    assert report["resolved_count"] == 509
    assert report["unresolved_blocking_count"] == 4
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 509,
        "unbound": 4,
    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [
        item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL
        and item.obligation_id not in bound
    ]
    assert len(unbound) == 4
    assert {item.source_ref for item in unbound} == {
        f"AC-{index:02d}" for index in range(1, 25)
    } - {"AC-09", "AC-11", "AC-12", "AC-13", "AC-14", "AC-15", "AC-20", "AC-22"}
