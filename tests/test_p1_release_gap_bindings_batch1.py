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
    derive_obligations,
    reconcile_repository,
)


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_HEAD = "cca2769f760d6bb703ad9153fd1cb4752e3c244c"
BOUND_AT = "2026-09-28T20:34:16Z"
REVIEW_AT = "2026-10-28T20:34:16Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED_IDS = {
    "P1-GAP-VOL-047:gap:c05917d472-9743acc54597c970",
    "P1-GAP-VOL-047:gap:dae485b0ab-95433d6f502b10b0",
    "P1-GAP-VOL-048:gap:9320a616bf-26130b42bc6434d2",
    "P1-GAP-VOL-048:gap:b7d2e51ff3-ceec1b6b658f6fb9",
    "P1-GAP-VOL-050:gap:0e5bfbf1cd-e783002e5d6bf21e",
    "P1-GAP-VOL-050:gap:8c4209a970-14e49691a16c75c4",
    "P1-GAP-VOL-060:gap:8d82de7c5e-5b80c23b01246bc9",
    "P1-GAP-VOL-060:gap:e5adc9105d-d9e41a36a8a16b79",
    "P1-GAP-VOL-064:gap:3465cee76d-5bcf48a4515fe8c0",
    "P1-GAP-VOL-065:gap:d78a7ae8f2-00ea556518764aa8",
    "P1-GAP-VOL-066:gap:72b45b8cdd-f18f5667520fec01",
    "P1-GAP-VOL-409:gap:23600aaf31-77db6101b7514063",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_batch1_registry_contains_only_exact_verified_gap_bindings() -> None:
    registry = _load(ROOT / REGISTRY)
    records = [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] == "release_gap_closure"
    ]

    assert len(records) == 12
    assert {row["obligation_id"] for row in records} == EXPECTED_IDS

    for row in records:
        assert row["owner_id"].startswith("ACC-VOL-")
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["bound_at"] == BOUND_AT
        assert row["review_at"] == REVIEW_AT
        assert row["accepted_risk"] is None
        assert len(row["evidence"]) == 1

        evidence = row["evidence"][0]
        assert evidence["category"] == "release_gap_closure"
        assert VERIFIER_HEAD in evidence["source"]
        assert row["obligation_id"] in evidence["source"]
        assert len(evidence["digest"]) == 64


def test_batch1_bindings_match_live_canonical_obligation_digests() -> None:
    master = _load(ROOT / MASTER)
    p1_map = _load(ROOT / P1_MAP)
    adversarial = _load(ROOT / ADVERSARIAL)
    policy = _load(ROOT / POLICY)
    registry = _load(ROOT / REGISTRY)

    obligations = {
        item.obligation_id: item
        for item in derive_obligations(
            master,
            p1_map,
            adversarial,
            policy,
        )
    }

    batch1 = [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] == "release_gap_closure"
    ]
    assert len(batch1) == 12

    for row in batch1:
        obligation = obligations[row["obligation_id"]]
        assert row["obligation_digest"] == obligation.obligation_digest
        assert obligation.kind.value == "gap"
        assert obligation.default_severity.value == "high"
        assert obligation.blocking_by_default is True


def test_batch1_remains_twelve_bindings_inside_combined_reconciliation() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["inventory"] == {
        "p1_primary_volume_count": 107,
        "volume_risk_count": 281,
        "volume_gap_count": 208,
        "applicable_adversarial_axis_count": 24,
        "total_obligation_count": 513,
    }
    assert report["binding_count"] == 494
    assert report["resolved_count"] == 494
    assert report["unresolved_blocking_count"] == 19
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 494,
        "unbound": 19,
    }


def test_batch1_does_not_delete_canonical_masterplan_gaps() -> None:
    master = _load(ROOT / MASTER)
    by_key = {row["key"]: row for row in master["volumes"]}

    expected = {
        "VOL-047": {
            "bind installer to release provenance",
            "materialize interruption checkpoints",
        },
        "VOL-048": {
            "define update compatibility graph",
            "bind migrations to restore/rollback proof",
        },
        "VOL-050": {
            "define ownership manifest from installer receipts",
            "materialize residual scanner",
        },
        "VOL-060": {
            "define release evidence bundle schema",
            "bind installer/updater artifacts to release digest",
        },
        "VOL-064": {"define backup coverage manifest"},
        "VOL-065": {"materialize full DR evidence bundle"},
        "VOL-066": {"bind postmortem actions into gap/risk ledgers"},
        "VOL-409": {"generate release notices"},
    }
    for key, statements in expected.items():
        assert statements <= set(by_key[key]["gaps"])
