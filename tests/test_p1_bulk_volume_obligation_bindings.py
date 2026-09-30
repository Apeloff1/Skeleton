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

VERIFIER_HEAD = "dfeaadc5da74c0205785adf2387c607603d9cdb4"
VERIFIER_RUN_ID = 36755041677
VERIFIER_JOB_ID = 110023019780
BOUND_AT = "2026-09-30T18:00:00Z"
REVIEW_AT = "2026-10-30T18:00:00Z"
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

    for row in rows:
        assert row["owner_id"].startswith("ACC-VOL-")
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["bound_at"] == BOUND_AT
        assert row["review_at"] == REVIEW_AT
        assert row["accepted_risk"] is None
        assert len(row["obligation_digest"]) == 64
        assert len(row["evidence"]) == 1

        evidence = row["evidence"][0]
        assert evidence["category"] == CATEGORY
        assert len(evidence["digest"]) == 64
        assert evidence["source"] == (
            "p1:bulk-volume-obligation-evidence:"
            + row["obligation_id"]
            + ":"
            + VERIFIER_HEAD
        )


def test_bulk_bindings_match_live_canonical_obligations() -> None:
    obligations = {item.obligation_id: item for item in _obligations()}

    for row in _bulk_records():
        obligation = obligations[row["obligation_id"]]
        assert row["obligation_digest"] == obligation.obligation_digest
        assert obligation.kind in {RiskKind.RISK, RiskKind.GAP}
        assert obligation.source_ref.split(":", 1)[0] in row["owner_id"]


def test_governed_frontier_is_489_resolved_24_adversarial() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 489
    assert report["resolved_count"] == 489
    assert report["unresolved_blocking_count"] == 24
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 489,
        "unbound": 24,
    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [item for item in _obligations() if item.obligation_id not in bound]

    assert len(unbound) == 24
    assert all(item.kind is RiskKind.ADVERSARIAL for item in unbound)
    assert {item.source_ref for item in unbound} == {
        f"AC-{index:02d}" for index in range(1, 25)
    }


def test_bulk_binding_does_not_mutate_masterplan_source_obligations() -> None:
    master = _load(ROOT / MASTER)
    by_key = {row["key"]: row for row in master["volumes"]}

    for row in _bulk_records():
        volume_key = row["owner_id"].removeprefix("ACC-")
        volume = by_key[volume_key]
        if row["obligation_id"].startswith("P1-RISK-"):
            assert any(
                item.obligation_id == row["obligation_id"]
                for item in _obligations()
                if item.kind is RiskKind.RISK
            )
            assert volume["risks"]
        else:
            assert any(
                item.obligation_id == row["obligation_id"]
                for item in _obligations()
                if item.kind is RiskKind.GAP
            )
            assert volume["gaps"]
