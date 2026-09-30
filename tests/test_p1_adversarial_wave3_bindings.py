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

VERIFIER_HEAD = "0f146f51fa3b4c7627904a0138e33ec4c0c3de32"
VERIFIER_RUN_ID = 36775355183
VERIFIER_JOB_ID = 110091774165
REPORT_DIGEST = "76f2fc5bab7cc36e12d7708a385e796cc4a0cc8316e323327c25b65f9349cb20"
BOUND_AT = "2026-09-30T20:55:00Z"
REVIEW_AT = "2026-10-30T20:55:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED = {
    "AC-02": ("P1-ADVERSARIAL-AC-02-7d64e5e5ff017e0d", "5ba1f09d93f34e95e575d2ece8a228c3d3a6922e8f87d39ccc26d0fce2abc1a3"),
    "AC-03": ("P1-ADVERSARIAL-AC-03-211e90dc21d34cd9", "489b8318a58f93afe0f8596b040f2063ed3a785597595e5f38b52d99887852c6"),
    "AC-04": ("P1-ADVERSARIAL-AC-04-662da77bdcf0a3c7", "9d9626a1e87403e4cc518726df2aea0efe33a5a0de25be5477eaa887ec1d90df"),
    "AC-05": ("P1-ADVERSARIAL-AC-05-a38d82bdc85e609d", "cb78a506b1fc4b411ade9639254257a19c92a9c3f67241e4890e69b9da4c9539"),
    "AC-06": ("P1-ADVERSARIAL-AC-06-df19f0b3509d9817", "dcbbb38d6595162b4a801dcc8986430a8398fcd0d93d184743ae41d6729ec45f"),
    "AC-07": ("P1-ADVERSARIAL-AC-07-a2990e55384a2d17", "a9fbcf1cc7cffe6563ed30f4ad762c0a789c77e59a936069d94c85041587d3e0"),
    "AC-18": ("P1-ADVERSARIAL-AC-18-78285cc6ad723979", "b9f35f59261deb42cf77661957e258e6c0387d6437b6a5b5cdc3015b298127da"),
    "AC-24": ("P1-ADVERSARIAL-AC-24-efcf5eaba6cb7e1d", "b7c5a1167165799da6982bbab75b192d94cbf09a34c468d4afbdc2ad49efc894"),
}
EXPECTED_MODES = {
    "AC-02": {"shutdown_race", "restart_replay", "fault_injection", "state_machine_property"},
    "AC-03": {"resource_exhaustion", "load_test", "soak", "degraded_mode"},
    "AC-04": {"dependency_fault", "fallback_matrix", "policy_regression", "provider_outage"},
    "AC-05": {"unknown_outcome_reconciliation", "idempotency_replay", "provider_fault", "receipt_recovery"},
    "AC-06": {"reconciliation_drill", "duplicate_delivery", "orphan_sweep", "projection_rebuild"},
    "AC-07": {"mixed_version", "upgrade_downgrade", "schema_compatibility", "rollback_rehearsal"},
    "AC-18": {"reindex_rebuild", "compaction", "deletion_replay", "derived_data_invalidation"},
    "AC-24": {"pairwise_fault_matrix", "compound_chaos", "recovery_replay", "signed_fault_bundle"},
}
RESIDUAL = {"AC-01", "AC-08", "AC-10", "AC-19", "AC-21", "AC-23"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wave3_bindings_pin_successful_exact_head_receipt() -> None:
    assert VERIFIER_RUN_ID == 36775355183
    assert VERIFIER_JOB_ID == 110091774165
    assert len(REPORT_DIGEST) == 64

    registry = _load(ROOT / REGISTRY)
    by_id = {row["obligation_id"]: row for row in registry["records"]}
    for axis_id, (obligation_id, digest) in EXPECTED.items():
        row = by_id[obligation_id]
        assert row["obligation_digest"] == digest
        assert row["owner_id"] == "ACC-P1-EVID-04"
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["bound_at"] == BOUND_AT
        assert row["review_at"] == REVIEW_AT
        assert row["accepted_risk"] is None
        assert {item["category"] for item in row["evidence"]} == EXPECTED_MODES[axis_id]
        for item in row["evidence"]:
            assert len(item["digest"]) == 64
            assert item["source"] == (
                f"p1:adversarial-wave3:{axis_id}:{item['category']}:{VERIFIER_HEAD}"
            )


def test_wave3_bindings_match_live_canonical_obligations() -> None:
    obligations = {
        item.source_ref: item
        for item in derive_obligations(
            _load(ROOT / MASTER),
            _load(ROOT / P1_MAP),
            _load(ROOT / ADVERSARIAL),
            _load(ROOT / POLICY),
        )
        if item.kind is RiskKind.ADVERSARIAL
    }
    for axis_id, (obligation_id, digest) in EXPECTED.items():
        obligation = obligations[axis_id]
        assert obligation.obligation_id == obligation_id
        assert obligation.obligation_digest == digest
        assert set(obligation.required_evidence_modes) == EXPECTED_MODES[axis_id]


def test_wave3_bindings_advance_frontier_to_507_6_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 507
    assert report["resolved_count"] == 507
    assert report["unresolved_blocking_count"] == 6
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 507, "unbound": 6}

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    obligations = derive_obligations(
        _load(ROOT / MASTER),
        _load(ROOT / P1_MAP),
        _load(ROOT / ADVERSARIAL),
        _load(ROOT / POLICY),
    )
    residual = {
        item.source_ref
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == RESIDUAL
