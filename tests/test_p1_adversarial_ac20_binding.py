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

AXIS_ID = "AC-20"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-20-80259972cf1cce6a"
OBLIGATION_DIGEST = "b87aca772977cd25d2eaa3d2f8e7dab7985166c56f231287aab45d26580dae84"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "2865b1785316a88e026a5e358d5aa7cedaea7ac5"
VERIFIER_RUN_ID = 36757293622
VERIFIER_JOB_ID = 110030645608
BOUND_AT = "2026-09-30T18:20:00Z"
REVIEW_AT = "2026-10-30T18:20:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED_EVIDENCE = {
    "drift_validator": "ddbe3822e3f3decbabb680b10148671d7aff1b2abb8edc5c0ab8d2bf45ce28b1",
    "architecture_fitness": "0ad5f04fa988c9d95aafe8061bfffeacc0d8945a4a5f08081f71f4a81d5d967d",
    "undeclared_component_scan": "fbd6e381a0cd5ba5e9c930be7d5866ea046de9c7470670f8828d7942a690175b",
    "traceability_check": "6671f5810dde65084f44d4d773208a2d7b739bc66c31d8244d22cbc181916408",
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


def test_ac20_binding_pins_successful_exact_head_verifier() -> None:
    row = _binding()

    assert VERIFIER_RUN_ID == 36757293622
    assert VERIFIER_JOB_ID == 110030645608
    assert row["obligation_digest"] == OBLIGATION_DIGEST
    assert row["owner_id"] == OWNER_ID
    assert row["severity"] == "high"
    assert row["disposition"] == "evidence"
    assert row["bound_at"] == BOUND_AT
    assert row["review_at"] == REVIEW_AT
    assert row["accepted_risk"] is None

    assert len(row["evidence"]) == 4
    by_category = {item["category"]: item for item in row["evidence"]}
    assert set(by_category) == set(EXPECTED_EVIDENCE)
    for category, digest in EXPECTED_EVIDENCE.items():
        evidence = by_category[category]
        assert evidence["digest"] == digest
        assert evidence["source"] == (
            f"p1:adversarial-ac20-evidence:{AXIS_ID}:"
            f"{category}:{VERIFIER_HEAD}"
        )


def test_ac20_binding_matches_live_adversarial_obligation() -> None:
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


def test_governed_frontier_is_497_resolved_16_adversarial() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    expected_total = report["inventory"]["total_obligation_count"]
    assert report["binding_count"] == expected_total
    assert report["resolved_count"] == expected_total
    assert report["unresolved_blocking_count"] == 0
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": expected_total,
    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [item for item in _obligations() if item.obligation_id not in bound]

    assert len(unbound) == 0
    assert all(item.kind is RiskKind.ADVERSARIAL for item in unbound)
    assert AXIS_ID not in {item.source_ref for item in unbound}
    assert {item.source_ref for item in unbound} == set()
