from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.reconcile_p1_risk_evidence import ADVERSARIAL, MASTER, P1_MAP, POLICY, REGISTRY, ROOT, RiskKind, derive_obligations, reconcile_repository

AXIS_ID = "AC-11"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-11-3d29c2151a6e3351"
OBLIGATION_DIGEST = "0c867539f12df396af4716514ff7abb81ba649ea020ccd285f99de27847a184a"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "9f7a70b8dda16e50d8c642165b0c90da9fed29db"
VERIFIER_RUN_ID = 36758958895
VERIFIER_JOB_ID = 110036293521
BOUND_AT = "2026-09-30T18:45:00Z"
REVIEW_AT = "2026-10-30T18:45:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "semantic_canary": "806c9b16e2361b498232189821337428d66da5ee00293024f853d15a7b4b745a",
    "contract_probe": "d57fc24f73d225383b70356364e9c9a2a22f7cbc0e7d6516a98b38b9f99a2d79",
    "drift_eval": "d823da5c04ff8b1abb70f3415f4bc57a13874a4fcee43e95be1594bcee5006fc",
    "evidence_invalidation": "2e003c962809a28c2901c732ddbd3147be2c62621316f9230747a570181ebd21",
}

def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _binding() -> dict:
    registry = _load(ROOT / REGISTRY)
    rows = [row for row in registry["records"] if row["obligation_id"] == OBLIGATION_ID]
    assert len(rows) == 1
    return rows[0]

def _obligation():
    items = derive_obligations(_load(ROOT / MASTER), _load(ROOT / P1_MAP), _load(ROOT / ADVERSARIAL), _load(ROOT / POLICY))
    rows = [item for item in items if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID]
    assert len(rows) == 1
    return rows[0]

def test_ac11_binding_pins_successful_verifier_receipt() -> None:
    row = _binding()
    assert VERIFIER_RUN_ID == 36758958895
    assert VERIFIER_JOB_ID == 110036293521
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
        assert by_category[category]["digest"] == digest
        assert by_category[category]["source"] == f"p1:adversarial-ac11-evidence:{AXIS_ID}:{category}:{VERIFIER_HEAD}"

def test_ac11_binding_matches_live_obligation() -> None:
    obligation = _obligation()
    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED)

def test_ac11_binding_advances_frontier_without_risk_acceptance() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 495
    assert report["resolved_count"] == 495
    assert report["unresolved_blocking_count"] == 18
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 495, "unbound": 18}
