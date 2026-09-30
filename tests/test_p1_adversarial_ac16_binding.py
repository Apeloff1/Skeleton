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
VERIFIER_HEAD = "f6d9ece188b96fcb752d8d41b7e31299f0e1c053"
VERIFIER_RUN_ID = 36784936908
VERIFIER_JOB_ID = 110123977852
REPORT_DIGEST = "23b9145e5ec08814ff1c388da64f8c2e0395d642bb08862a889dc2d96e85569c"
BOUND_AT = "2026-09-30T22:00:00Z"
REVIEW_AT = "2026-10-30T22:00:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "telemetry_outage": "27245f773b1437957a3ab5213b133193927b9923dca8b5944839a9f14d593a6f",
    "cardinality_bomb": "c95aaebd65d644665b5c08b69abbdc8de65bec41f6b0b10a8baf0af5e359e3b4",
    "redaction_test": "e39123691602d49333baa6e7b371a9272d6b48318e92122c454f212366ea1fe0",
    "reconstruction_without_full_telemetry": "b6e01e753281ac37f131c41cb8689ffe8c1365470b0d1c9d6fa36f1e06143a9d",
}
RESIDUAL: set[str] = set()


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
    assert VERIFIER_RUN_ID == 36784936908
    assert VERIFIER_JOB_ID == 110123977852
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


def test_ac16_binding_advances_frontier_to_513_0_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 513
    assert report["resolved_count"] == 513
    assert report["unresolved_blocking_count"] == 0
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 513}

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    residual = {
        item.source_ref
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == RESIDUAL
