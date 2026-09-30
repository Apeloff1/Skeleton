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

AXIS_ID = "AC-15"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-15-f7f89f2c5b94ede2"
OBLIGATION_DIGEST = "f40e7b2b95b734e8fad7419baa251d47e9e05a3ec343f677d0a6e93fa7dab98d"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "32d7f55345db9f081ed8c6a8adb72a7012489e27"
VERIFIER_RUN_ID = 36758921559
VERIFIER_JOB_ID = 110036166551
BOUND_AT = "2026-09-30T18:36:00Z"
REVIEW_AT = "2026-10-30T18:36:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED_EVIDENCE = {
    "budget_fault": "1f824dd862945c00e379e256dd0613a4c35e0a78c74cc8b4097899a624b677d2",
    "fanout_stress": "38856b532fe1671f5a9d06b456b2ca81fa7c7b6d834673d7a1e5422ff480a88b",
    "quota_isolation": "2b6a39fdb1f6ffa6f41edd55ca25c045770888e81c1d571ffe61a99c401206ee",
    "provider_reprice_simulation": "6cb6f58f37905309803f8a3fe990c977d29a1e250143f1234906f287ee0c3e44",
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


def test_ac15_binding_pins_successful_exact_head_verifier() -> None:
    row = _binding()

    assert VERIFIER_RUN_ID == 36758921559
    assert VERIFIER_JOB_ID == 110036166551
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
            f"p1:adversarial-ac15-evidence:{AXIS_ID}:"
            f"{category}:{VERIFIER_HEAD}"
        )


def test_ac15_binding_matches_live_adversarial_obligation() -> None:
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


def test_governed_frontier_is_491_resolved_22_adversarial() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 491
    assert report["resolved_count"] == 491
    assert report["unresolved_blocking_count"] == 22
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 491,
        "unbound": 22,
    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [item for item in _obligations() if item.obligation_id not in bound]

    assert len(unbound) == 22
    assert all(item.kind is RiskKind.ADVERSARIAL for item in unbound)
    assert {item.source_ref for item in unbound} == {
        f"AC-{index:02d}" for index in range(1, 25)
    } - {"AC-15", "AC-20"}
