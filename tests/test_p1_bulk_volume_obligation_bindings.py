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
    retired_gap_owner_from_id,
)

VERIFIER_HEAD = "dfeaadc5da74c0205785adf2387c607603d9cdb4"
VERIFIER_RUN_ID = 36755041677
VERIFIER_JOB_ID = 110023019780
BOUND_AT = "2026-09-30T18:00:00Z"
REVIEW_AT = "2026-10-30T18:00:00Z"
REBOUND_VERIFIER_HEAD = "bebff9e9c0ea2e9f1f24d2fb4e0c1bbcea4dac2d"
REBOUND_AT = "2026-10-06T19:28:13Z"
REBOUND_REVIEW_AT = "2026-11-05T19:28:13Z"
REBOUND_OBLIGATION_IDS = frozenset({
    "P1-GAP-VOL-008:gap:0fb088140e-733f82e58e6474c6",
    "P1-GAP-VOL-009:gap:c8aa33cfa3-679d49dbbd2ef60d",
    "P1-GAP-VOL-012:gap:7c9fbd97d7-593b4d226d62b6f6",
    "P1-GAP-VOL-012:gap:fb855ce6d8-320322fb17a1718e",
})
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
CATEGORY = "p1_volume_obligation_evidence"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bulk_records() -> list[dict]:
    registry = _load(ROOT / REGISTRY)
    return [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] == CATEGORY
    ]


def _obligations():
    return derive_obligations(
        _load(ROOT / MASTER),
        _load(ROOT / P1_MAP),
        _load(ROOT / ADVERSARIAL),
        _load(ROOT / POLICY),
    )


def test_bulk_binding_provenance_is_exact_and_complete() -> None:
    rows = _bulk_records()

    assert len(rows) == 455
    assert len({row["obligation_id"] for row in rows}) == 455
    assert sum(row["obligation_id"].startswith("P1-RISK-") for row in rows) == 269
    assert sum(row["obligation_id"].startswith("P1-GAP-") for row in rows) == 186
    assert VERIFIER_RUN_ID == 36755041677
    assert VERIFIER_JOB_ID == 110023019780

    rebound_ids = {row["obligation_id"] for row in rows if row["obligation_id"] in REBOUND_OBLIGATION_IDS}
    assert rebound_ids == REBOUND_OBLIGATION_IDS

    for row in rows:
        assert row["owner_id"].startswith("ACC-VOL-")
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        rebound = row["obligation_id"] in REBOUND_OBLIGATION_IDS
        assert row["bound_at"] == (REBOUND_AT if rebound else BOUND_AT)
        assert row["review_at"] == (
            REBOUND_REVIEW_AT if rebound else REVIEW_AT
        )
        assert row["accepted_risk"] is None
        assert len(row["obligation_digest"]) == 64
        assert len(row["evidence"]) == 1

        evidence = row["evidence"][0]
        assert evidence["category"] == CATEGORY
        assert len(evidence["digest"]) == 64
        expected_head = REBOUND_VERIFIER_HEAD if rebound else VERIFIER_HEAD
        assert evidence["source"] == (
            "p1:bulk-volume-obligation-evidence:"
            + row["obligation_id"]
            + ":"
            + expected_head
        )


def test_bulk_bindings_match_live_or_governed_retired_obligations() -> None:
    obligations = {item.obligation_id: item for item in _obligations()}
    retired = []

    for row in _bulk_records():
        obligation = obligations.get(row["obligation_id"])
        if obligation is None:
            retired.append(row)
            assert row["obligation_id"].startswith("P1-GAP-")
            assert retired_gap_owner_from_id(row["obligation_id"]) == row["owner_id"]
            assert row["disposition"] == "evidence"
            assert row["evidence"]
            assert row["accepted_risk"] is None
            continue

        assert row["obligation_digest"] == obligation.obligation_digest
        assert obligation.kind in {RiskKind.RISK, RiskKind.GAP}
        assert obligation.source_ref.split(":", 1)[0] in row["owner_id"]

    assert retired
    assert all(row["obligation_id"].startswith("P1-GAP-") for row in retired)


def test_governed_frontier_is_497_resolved_16_adversarial() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 513
    assert report["resolved_count"] == 513
    assert report["unresolved_blocking_count"] == 0
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 513,

    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [item for item in _obligations() if item.obligation_id not in bound]

    assert len(unbound) == 0
    assert all(item.kind is RiskKind.ADVERSARIAL for item in unbound)
    assert {item.source_ref for item in unbound} == set()


def test_bulk_binding_does_not_mutate_masterplan_source_obligations() -> None:
    master = _load(ROOT / MASTER)
    by_key = {row["key"]: row for row in master["volumes"]}
    obligations = {item.obligation_id: item for item in _obligations()}

    for row in _bulk_records():
        volume_key = row["owner_id"].removeprefix("ACC-")
        volume = by_key[volume_key]
        obligation = obligations.get(row["obligation_id"])

        if row["obligation_id"].startswith("P1-RISK-"):
            assert obligation is not None
            assert obligation.kind is RiskKind.RISK
            assert volume["risks"]
            continue

        if obligation is not None:
            assert obligation.kind is RiskKind.GAP
            assert volume["gaps"]
            continue

        assert retired_gap_owner_from_id(row["obligation_id"]) == row["owner_id"]
        assert row["disposition"] == "evidence"
        assert row["evidence"]
        assert row["accepted_risk"] is None
