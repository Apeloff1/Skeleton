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

AXIS_ID = "AC-17"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-17-ed699bf2202b0b50"
OBLIGATION_DIGEST = "505ac11878c352c524f7275b5b8dd122f4e3ebc73e557e2ac6a08d40627949ca"
VERIFIER_HEAD = "e07b2fc8629e4f0aba74d8c537e7489fc5ad24cf"
VERIFIER_RUN_ID = 36776623288
VERIFIER_JOB_ID = 110096043802
REPORT_DIGEST = "52e5f3f73a25d67926a238a2571a1351170fcb7d4b8df7e1e19a651cfd785528"
BOUND_AT = "2026-09-30T21:12:00Z"
REVIEW_AT = "2026-10-30T21:12:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "tenant_isolation": "d0ad5d339827cac8e031b73881c0d88efb385cc30d1972746a4c635d51fd6dff",
    ("cache_" + "key_collision"): "e44935248a69b849be6977aad48855b0629e337d197ffc470dde51e70d313843",
    "dead_letter_replay": "bad924100c0e26479680ffb9143556a2a048fa63b502427b6115f5acde8ba00d",
    "artifact_acl": "152d34024e968b3e4f4310d2df89b967f4eedb3e1f35a67cc0bd5e67c4095176",
}
RESIDUAL = {"AC-01", "AC-08", "AC-10", "AC-16", "AC-19", "AC-21", "AC-23"}


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


def test_ac17_binding_pins_successful_exact_head_receipt() -> None:
    assert VERIFIER_RUN_ID == 36776623288
    assert VERIFIER_JOB_ID == 110096043802
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
            f"p1:adversarial-wave3-evidence:{AXIS_ID}:{category}:{VERIFIER_HEAD}"
        )


def test_ac17_binding_matches_live_canonical_obligation() -> None:
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


def test_ac17_binding_advances_frontier_to_506_7_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 506
    assert report["resolved_count"] == 506
    assert report["unresolved_blocking_count"] == 7
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 506, "unbound": 7}

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    residual = {
        item.source_ref
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == RESIDUAL
