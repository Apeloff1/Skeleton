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

AXIS_ID = "AC-16"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-16-2a23277d73b91c0b"
OBLIGATION_DIGEST = "8e1485cc8a1644fa68cf0e038905e787fe615b7154263b9c21718927eb6caca1"
VERIFIER_HEAD = "c38d6a97de32fe9c4ddab194bad099623714b649"
VERIFIER_RUN_ID = 36782771511
VERIFIER_JOB_ID = 110116845210
REPORT_DIGEST = "c08b6a0d5912e1b1d07c9545c77c03200d91a894efe6c9e0bf4488bc8b68c50a"
BOUND_AT = "2026-09-30T22:00:00Z"
REVIEW_AT = "2026-10-30T22:00:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "telemetry_outage": "8225c72fa7160e0b2d24e8586c52cd1dd933140a25559c8b0d819645d3969201",
    "cardinality_bomb": "7f0b6f3387cdc894f1267e355841192e62c6881f6841af5607922524cf8295e7",
    "redaction_test": "6536921759d213dff2eb558a0258e5a77641f86d4017782a234f69e5d54002b5",
    "reconstruction_without_full_telemetry": "389108eacf53e236d8d0c09398a78551b68af70ac68223285280efed144faffe",
}
RESIDUAL = {"AC-01", "AC-08", "AC-10", "AC-21"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _binding() -> dict:
    registry = _load(ROOT / REGISTRY)
    rows = [row for row in registry["records"] if row["obligation_id"] == OBLIGATION_ID]
    assert len(rows) == 1
    return rows[0]


def _obligations():
    return derive_obligations(
        _load(ROOT / MASTER),
        _load(ROOT / P1_MAP),
        _load(ROOT / ADVERSARIAL),
        _load(ROOT / POLICY),
    )


def test_ac16_binding_pins_successful_exact_head_receipt() -> None:
    assert VERIFIER_RUN_ID == 36782771511
    assert VERIFIER_JOB_ID == 110116845210
    assert len(REPORT_DIGEST) == 64

    row = _binding()
    assert row["obligation_id"] == OBLIGATION_ID
    assert row["obligation_digest"] == OBLIGATION_DIGEST
    assert row["owner_id"] == "ACC-P1-EVID-04"
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
            f"p1:adversarial-ac16-evidence:{AXIS_ID}:{category}:{VERIFIER_HEAD}"
        )


def test_ac16_binding_matches_live_canonical_obligation() -> None:
    rows = [
        item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    assert len(rows) == 1
    obligation = rows[0]
    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED)


def test_ac16_binding_advances_frontier_to_509_4_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 509
    assert report["resolved_count"] == 509
    assert report["unresolved_blocking_count"] == 4
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 509, "unbound": 4}

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    residual = {
        item.source_ref
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == RESIDUAL
