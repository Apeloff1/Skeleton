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

AXIS_ID = "AC-09"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-09-81fa5fab73acd823"
OBLIGATION_DIGEST = "5d866e90ebbdba4e26b9f24b6aa42794f273130a24fce46df4984f034d984c50"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "75275748906e00717f06f944d0c99d0dc6f5c962"
VERIFIER_RUN_ID = 36773407012
VERIFIER_JOB_ID = 110085203668
REPORT_DIGEST = "1a9a58ccbb18dfd59b9faab8b175152aa137faf0d157c3eabb6ea93db9ba8c93"
BOUND_AT = "2026-09-30T20:34:00Z"
REVIEW_AT = "2026-10-30T20:34:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "clock_skew": "ebcbedea23563a43882148562273d28e8d2d7ee6c40647f4756a9671a1044a44",
    "suspend_resume": "da0640349f7afd7ea62526fb40e1115ee16e413acbce11b427e41d95994c8e31",
    "lease_fencing": "d897ce6e204f1f5f0a45c234168fd84a5ecbfd694476fdffe9dafa2de0cf26d5",
    "expiry_property": "ad0d810561314677bcb93b16e8b962e445829d8af7c1346e458cd2823ff73721",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _binding() -> dict:
    registry = _load(ROOT / REGISTRY)
    rows = [row for row in registry["records"] if row["obligation_id"] == OBLIGATION_ID]
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
        item for item in items
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    assert len(rows) == 1
    return rows[0]


def test_ac09_binding_pins_successful_exact_head_verifier() -> None:
    row = _binding()
    assert VERIFIER_RUN_ID == 36773407012
    assert VERIFIER_JOB_ID == 110085203668
    assert len(REPORT_DIGEST) == 64
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
            f"p1:adversarial-ac09-evidence:{AXIS_ID}:{category}:{VERIFIER_HEAD}"
        )


def test_ac09_binding_matches_live_canonical_obligation() -> None:
    obligation = _obligation()
    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED)


def test_ac09_binding_advances_frontier_without_risk_acceptance() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 513
    assert report["resolved_count"] == 513
    assert report["unresolved_blocking_count"] == 0
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 513}
