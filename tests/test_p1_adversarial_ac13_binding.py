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

AXIS_ID = "AC-13"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-13-0765da9a17a8326d"
OBLIGATION_DIGEST = "c35d0b3a1ae2045b89199ed6132937c23f6fbbac52dc3c492aeeeef508c3e735"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "8435144dcee7fcb087ad9806504d2d38c9094147"
VERIFIER_RUN_ID = 36763669209
VERIFIER_JOB_ID = 110052302630
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "fuzz": "9d61662c531f7df2bde6f4781f67bb4eb055f8987bf1ffd091b0fc5ba31536e4",
    "parser_limits": "9d1eb214a068510b06399c1dde76fe6ad00731ff3486bf64ffe245f6e95f83c1",
    "decompression_bomb": "f5d3d691340ce80e0564ae744b6959d469d50c468b057b368a6858d461197021",
    "complexity_budget": "58a85997b9cff610e15f6c05370083536d4d9628ea5a62fda562d48ebe594fe9",
}

def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _binding() -> dict:
    rows = [
        row
        for row in _load(ROOT / REGISTRY)["records"]
        if row["obligation_id"] == OBLIGATION_ID
    ]
    assert len(rows) == 1
    return rows[0]

def _obligation():
    rows = [
        item
        for item in derive_obligations(
            _load(ROOT / MASTER),
            _load(ROOT / P1_MAP),
            _load(ROOT / ADVERSARIAL),
            _load(ROOT / POLICY),
        )
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    assert len(rows) == 1
    return rows[0]

def test_ac13_binding_pins_successful_exact_head_receipt() -> None:
    row = _binding()
    assert VERIFIER_RUN_ID == 36763669209
    assert VERIFIER_JOB_ID == 110052302630
    assert row["obligation_digest"] == OBLIGATION_DIGEST
    assert row["owner_id"] == OWNER_ID
    assert row["severity"] == "high"
    assert row["disposition"] == "evidence"
    assert row["accepted_risk"] is None
    by_category = {item["category"]: item for item in row["evidence"]}
    assert set(by_category) == set(EXPECTED)
    for category, digest in EXPECTED.items():
        assert by_category[category]["digest"] == digest
        assert by_category[category]["source"] == (
            f"p1:adversarial-ac13-evidence:{AXIS_ID}:{category}:{VERIFIER_HEAD}"
        )

def test_ac13_binding_matches_live_obligation() -> None:
    obligation = _obligation()
    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED)

def test_ac13_binding_advances_frontier_to_494_19_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 494
    assert report["resolved_count"] == 494
    assert report["unresolved_blocking_count"] == 19
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 494, "unbound": 19}

    bound = {row["obligation_id"] for row in _load(ROOT / REGISTRY)["records"]}
    unbound = {
        item.source_ref
        for item in derive_obligations(
            _load(ROOT / MASTER),
            _load(ROOT / P1_MAP),
            _load(ROOT / ADVERSARIAL),
            _load(ROOT / POLICY),
        )
        if item.kind is RiskKind.ADVERSARIAL
        and item.obligation_id not in bound
    }
    assert len(unbound) == 19
    assert AXIS_ID not in unbound
