from __future__ import annotations

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.knowledge_store import (
    ClaimLifecycle,
    KnowledgeClaim,
    KnowledgeStoreError,
    TemporalKnowledgeStore,
    VerificationState,
)


def _evidence(tag: str) -> tuple[EvidenceRef, ...]:
    digest_char = tag[0] if tag[0] in "abcdef" else "a"
    return (
        EvidenceRef(
            source=f"source://{tag}",
            digest=digest_char * 64,
            category="knowledge-evidence",
        ),
    )


def _claim(
    claim_id: str,
    object_value: str,
    *,
    confidence: float,
    verification: VerificationState,
) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=claim_id,
        revision=1,
        tenant_id="tenant-a",
        scope_key="project-x",
        subject="service-a",
        predicate="deployment-region",
        object_value=object_value,
        source_id=f"source-{claim_id}",
        source_revision="r1",
        valid_from=0.0,
        valid_to=None,
        recorded_at=10.0,
        confidence=confidence,
        verification_state=verification,
        evidence=_evidence(claim_id),
    )


def test_confidence_verification_are_independent_and_conflicts_survive() -> None:
    store = TemporalKnowledgeStore()
    first = _claim(
        "claim-a",
        "eu-west",
        confidence=0.99,
        verification=VerificationState.UNVERIFIED,
    )
    second = _claim(
        "claim-b",
        "eu-north",
        confidence=0.60,
        verification=VerificationState.SUPPORTED,
    )
    store.append(
        first,
        operation_id="append-a",
        expected_store_digest=store.store_digest,
        evidence=_evidence("append-a"),
    )
    store.append(
        second,
        operation_id="append-b",
        expected_store_digest=store.store_digest,
        evidence=_evidence("append-b"),
    )

    snapshot = store.snapshot(
        tenant_id="tenant-a",
        scope_key="project-x",
        as_of=20.0,
    )
    by_id = {item.claim_id: item for item in snapshot.claims}
    assert set(by_id) == {"claim-a", "claim-b"}
    assert snapshot.conflicts
    assert set(snapshot.conflicts[0].object_values) == {"eu-west", "eu-north"}
    assert by_id["claim-a"].confidence > by_id["claim-b"].confidence
    assert by_id["claim-a"].verification_state is VerificationState.UNVERIFIED
    assert by_id["claim-b"].verification_state is VerificationState.SUPPORTED


def test_append_replay_is_idempotent() -> None:
    store = TemporalKnowledgeStore()
    claim = _claim(
        "claim-a",
        "eu-west",
        confidence=0.8,
        verification=VerificationState.SUPPORTED,
    )
    expected = store.store_digest
    first = store.append(
        claim,
        operation_id="append-a",
        expected_store_digest=expected,
        evidence=_evidence("append-a"),
    )
    replay = store.append(
        claim,
        operation_id="append-a",
        expected_store_digest=expected,
        evidence=_evidence("append-a"),
    )
    assert replay.receipt_digest == first.receipt_digest
    assert len(store.history("claim-a")) == 1


def test_revision_is_exact_store_and_head_fenced() -> None:
    store = TemporalKnowledgeStore()
    claim = _claim(
        "claim-a",
        "eu-west",
        confidence=0.8,
        verification=VerificationState.UNVERIFIED,
    )
    store.append(
        claim,
        operation_id="append-a",
        expected_store_digest=store.store_digest,
        evidence=_evidence("append-a"),
    )

    with pytest.raises(KnowledgeStoreError, match="stale knowledge store digest"):
        store.revise(
            "claim-a",
            operation_id="revise-stale-store",
            expected_store_digest="0" * 64,
            expected_head_digest=store.head("claim-a").revision_digest,
            recorded_at=20.0,
            source_revision="r2",
            evidence=_evidence("revise-a"),
            verification_state=VerificationState.SUPPORTED,
        )

    with pytest.raises(KnowledgeStoreError, match="stale claim head digest"):
        store.revise(
            "claim-a",
            operation_id="revise-stale-head",
            expected_store_digest=store.store_digest,
            expected_head_digest="0" * 64,
            recorded_at=20.0,
            source_revision="r2",
            evidence=_evidence("revise-b"),
            verification_state=VerificationState.SUPPORTED,
        )


def test_revision_replay_remains_idempotent_after_head_advances() -> None:
    store = TemporalKnowledgeStore()
    claim = _claim(
        "claim-a",
        "eu-west",
        confidence=0.8,
        verification=VerificationState.UNVERIFIED,
    )
    store.append(
        claim,
        operation_id="append-a",
        expected_store_digest=store.store_digest,
        evidence=_evidence("append-a"),
    )
    expected_store = store.store_digest
    expected_head = store.head("claim-a").revision_digest
    first = store.revise(
        "claim-a",
        operation_id="revise-a",
        expected_store_digest=expected_store,
        expected_head_digest=expected_head,
        recorded_at=20.0,
        source_revision="r2",
        evidence=_evidence("revise-a"),
        verification_state=VerificationState.SUPPORTED,
        confidence=0.75,
    )
    replay = store.revise(
        "claim-a",
        operation_id="revise-a",
        expected_store_digest=expected_store,
        expected_head_digest=expected_head,
        recorded_at=20.0,
        source_revision="r2",
        evidence=_evidence("revise-a"),
        verification_state=VerificationState.SUPPORTED,
        confidence=0.75,
    )
    assert replay.receipt_digest == first.receipt_digest
    assert len(store.history("claim-a")) == 2


def test_tombstone_preserves_historical_truth_without_resurrection() -> None:
    store = TemporalKnowledgeStore()
    claim = _claim(
        "claim-a",
        "eu-west",
        confidence=0.8,
        verification=VerificationState.SUPPORTED,
    )
    store.append(
        claim,
        operation_id="append-a",
        expected_store_digest=store.store_digest,
        evidence=_evidence("append-a"),
    )
    store.tombstone(
        "claim-a",
        operation_id="delete-a",
        expected_store_digest=store.store_digest,
        expected_head_digest=store.head("claim-a").revision_digest,
        recorded_at=30.0,
        source_revision="r-delete",
        evidence=_evidence("delete-a"),
    )

    historical = store.snapshot(
        tenant_id="tenant-a",
        scope_key="project-x",
        as_of=20.0,
    )
    current = store.snapshot(
        tenant_id="tenant-a",
        scope_key="project-x",
        as_of=40.0,
    )
    assert [item.claim_id for item in historical.claims] == ["claim-a"]
    assert current.claims == ()
    assert store.head("claim-a").lifecycle is ClaimLifecycle.TOMBSTONED
    assert len(store.history("claim-a")) == 2


def test_temporal_revisions_reject_time_rollback_and_tombstone_resurrection() -> None:
    store = TemporalKnowledgeStore()
    claim = _claim(
        "claim-a",
        "eu-west",
        confidence=0.8,
        verification=VerificationState.SUPPORTED,
    )
    store.append(
        claim,
        operation_id="append-a",
        expected_store_digest=store.store_digest,
        evidence=_evidence("append-a"),
    )
    with pytest.raises(KnowledgeStoreError, match="recorded_at cannot move backward"):
        store.revise(
            "claim-a",
            operation_id="revise-backward",
            expected_store_digest=store.store_digest,
            expected_head_digest=store.head("claim-a").revision_digest,
            recorded_at=5.0,
            source_revision="r-backward",
            evidence=_evidence("revise-a"),
        )

    store.tombstone(
        "claim-a",
        operation_id="delete-a",
        expected_store_digest=store.store_digest,
        expected_head_digest=store.head("claim-a").revision_digest,
        recorded_at=30.0,
        source_revision="r-delete",
        evidence=_evidence("delete-a"),
    )
    with pytest.raises(KnowledgeStoreError, match="tombstoned claim cannot be revised"):
        store.revise(
            "claim-a",
            operation_id="revise-after-delete",
            expected_store_digest=store.store_digest,
            expected_head_digest=store.head("claim-a").revision_digest,
            recorded_at=40.0,
            source_revision="r-resurrect",
            evidence=_evidence("revise-b"),
        )
