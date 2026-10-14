from __future__ import annotations

from dataclasses import replace
import hashlib
import math

import pytest

from skeleton.contracts.canonical import canonical_json_bytes

from skeleton.knowledge.store import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeStore,
    VerificationState,
)


def _evidence(source: str = "source://a") -> KnowledgeEvidence:
    return KnowledgeEvidence(source=source, digest="a" * 64, observed_at=100.0)


def _claim(**changes) -> KnowledgeClaim:
    values = dict(
        claim_id="claim-a",
        scope_key="tenant-a/project-a",
        subject="earth",
        predicate="shape",
        value_digest="1" * 64,
        confidence=0.99,
        verification=VerificationState.VERIFIED,
        evidence=(_evidence(),),
        recorded_at=101.0,
    )
    values.update(changes)
    return KnowledgeClaim(**values)


def test_conflicting_claims_coexist_and_are_explicit() -> None:
    store = KnowledgeStore()
    store.record(_claim())
    store.record(_claim(claim_id="claim-b", value_digest="2" * 64, confidence=0.51))

    view = store.query(scope_key="tenant-a/project-a", subject="earth", predicate="shape")

    assert [claim.claim_id for claim in view.claims] == ["claim-a", "claim-b"]
    assert view.conflicting is True
    assert len(view.snapshot_digest) == 64


def test_confidence_cannot_manufacture_verification() -> None:
    claim = _claim(
        confidence=1.0,
        verification=VerificationState.UNVERIFIED,
        evidence=(),
    )
    assert claim.confidence == 1.0
    assert claim.verification is VerificationState.UNVERIFIED

    with pytest.raises(ValueError, match="requires evidence"):
        replace(claim, verification=VerificationState.VERIFIED)


def test_claim_id_collision_fails_closed() -> None:
    store = KnowledgeStore()
    first = _claim()
    assert store.record(first) == store.record(first)

    with pytest.raises(ValueError, match="collision"):
        store.record(replace(first, value_digest="f" * 64))


def test_evidence_order_and_duplicates_do_not_change_identity() -> None:
    left = _evidence("source://left")
    right = KnowledgeEvidence(source="source://right", digest="b" * 64, observed_at=99.0)
    first = _claim(evidence=(right, left, right))
    second = _claim(evidence=(left, right))
    assert first.evidence == second.evidence
    assert first.identity == second.identity


def test_snapshot_round_trip_is_deterministic_and_tamper_evident() -> None:
    store = KnowledgeStore()
    store.record(_claim(claim_id="z"))
    store.record(_claim(claim_id="a", value_digest="2" * 64))

    snapshot = store.snapshot()
    restored = KnowledgeStore.from_snapshot(snapshot)

    assert restored.snapshot() == snapshot
    assert [row["claim_id"] for row in snapshot["claims"]] == ["a", "z"]

    tampered = dict(snapshot)
    tampered["claims"] = [dict(row) for row in snapshot["claims"]]
    tampered["claims"][0]["confidence"] = 0.01
    with pytest.raises(ValueError, match="digest mismatch"):
        KnowledgeStore.from_snapshot(tampered)


def test_scope_isolation_prevents_cross_tenant_conflict() -> None:
    store = KnowledgeStore()
    store.record(_claim())
    store.record(_claim(claim_id="claim-b", scope_key="tenant-b/project-a", value_digest="2" * 64))

    left = store.query(scope_key="tenant-a/project-a", subject="earth", predicate="shape")
    right = store.query(scope_key="tenant-b/project-a", subject="earth", predicate="shape")

    assert left.conflicting is False
    assert right.conflicting is False
    assert left.claims[0].claim_id == "claim-a"
    assert right.claims[0].claim_id == "claim-b"


def test_rejected_claim_does_not_create_active_conflict_but_remains_historical() -> None:
    store = KnowledgeStore()
    store.record(_claim())
    store.record(_claim(
        claim_id="claim-rejected",
        value_digest="9" * 64,
        verification=VerificationState.REJECTED,
    ))

    view = store.query(scope_key="tenant-a/project-a", subject="earth", predicate="shape")
    assert len(view.claims) == 2
    assert view.conflicting is False


def test_snapshot_digest_uses_shared_canonical_contract_bytes() -> None:
    store = KnowledgeStore()
    store.record(_claim())
    snapshot = store.snapshot()
    body = {"version": snapshot["version"], "claims": snapshot["claims"]}
    assert snapshot["snapshot_digest"] == hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def test_snapshot_restore_rejects_non_finite_values_fail_closed() -> None:
    store = KnowledgeStore()
    store.record(_claim())
    snapshot = store.snapshot()
    snapshot["claims"][0]["confidence"] = math.nan
    with pytest.raises(ValueError, match="strict canonical JSON"):
        KnowledgeStore.from_snapshot(snapshot)
