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

AXIS_ID = "AC-12"
OBLIGATION_ID = "P1-ADVERSARIAL-AC-12-09b6e9954d4be1de"
OBLIGATION_DIGEST = "e793561bdc5731f9d3d82d16c21f7e554f25b242bfd742586793d5d87b8c2afe"
OWNER_ID = "ACC-P1-EVID-04"
VERIFIER_HEAD = "3755ce81ddf80263e68e38e07acd4a2fa8853271"
VERIFIER_RUN_ID = 36771829006
VERIFIER_JOB_ID = 110079877271
REPORT_DIGEST = "7f3a0ce490ed0f94fdf18040ffde3c1ffa0ecf2a20ac8be4c72b7beecf29d194"
BOUND_AT = "2026-09-30T20:20:00Z"
REVIEW_AT = "2026-10-30T20:20:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
EXPECTED = {
    "canonicalization_fuzz": "b433bf8854f73ba4fcbd3a0077e28fcaa00a4d1372f2536c31b82c500ea529a9",
    "toctou_race": "7081d5e8fd403d8ddbd6855c9bee21a8a871ec19d0410b8fe1cb82a992f91c25",
    "resource_binding": "f8daec812f1c5bb9cf786cc41ce0a2b6f2635ffa4125c571e68a119f9584f424",
    "path_network_adversarial": "f05b90edf32d9fc18f6f1b6cbcd5f543482c0e9a45d8b762f8ce76bcacee023e",
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
        item
        for item in items
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    assert len(rows) == 1
    return rows[0]


def test_ac12_binding_pins_successful_exact_head_verifier() -> None:
    row = _binding()

    assert VERIFIER_RUN_ID == 36771829006
    assert VERIFIER_JOB_ID == 110079877271
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
            f"p1:adversarial-ac12-evidence:{AXIS_ID}:{category}:{VERIFIER_HEAD}"
        )


def test_ac12_binding_matches_live_canonical_obligation() -> None:
    obligation = _obligation()
    assert obligation.obligation_id == OBLIGATION_ID
    assert obligation.obligation_digest == OBLIGATION_DIGEST
    assert set(obligation.required_evidence_modes) == set(EXPECTED)


def test_ac12_binding_advances_frontier_without_risk_acceptance() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 507
    assert report["resolved_count"] == 507
    assert report["unresolved_blocking_count"] == 6
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 507, "unbound": 6}
