"""Memory reconciliation must be deterministic and deletion must propagate completely."""

import copy

import pytest

from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryQualityPolicy,
    MemoryRecord,
    MemoryReconciler,
    TombstoneLedger,
)


def _record(
    record_id: str = "m1",
    *,
    confidence: float = 0.9,
    importance: float = 0.9,
    access_count: int = 5,
    provenance_count: int = 3,
    contradiction_count: int = 0,
    last_accessed_at: float = 90.0,
    derived_targets=("embedding:m1", "index:m1"),
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        memory_class="semantic",
        created_at=0.0,
        updated_at=50.0,
        last_accessed_at=last_accessed_at,
        confidence=confidence,
        importance=importance,
        access_count=access_count,
        provenance_count=provenance_count,
        contradiction_count=contradiction_count,
        derived_targets=tuple(derived_targets),
    )


def test_high_quality_recent_memory_is_retained() -> None:
    reconciler = MemoryReconciler(
        MemoryQualityPolicy(half_life_s=100.0)
    )
    decision = reconciler.evaluate(_record(), now=100.0)

    assert decision.action is MemoryAction.RETAIN
    assert decision.score >= reconciler.policy.retain_threshold


def test_hard_contradiction_limit_forces_tombstone() -> None:
    policy = MemoryQualityPolicy(
        half_life_s=100.0,
        hard_contradiction_limit=2,
    )
    decision = MemoryReconciler(policy).evaluate(
        _record(contradiction_count=2),
        now=100.0,
    )

    assert decision.action is MemoryAction.TOMBSTONE
    assert "hard-contradiction-limit" in decision.reasons


def test_stale_unprovenanced_unused_memory_requires_review_or_tombstone() -> None:
    policy = MemoryQualityPolicy(
        half_life_s=10.0,
        retain_threshold=0.6,
        tombstone_threshold=0.1,
    )
    record = _record(
        confidence=0.5,
        importance=0.5,
        access_count=0,
        provenance_count=0,
        last_accessed_at=0.0,
    )

    decision = MemoryReconciler(policy).evaluate(record, now=100.0)

    assert decision.action in {MemoryAction.REVIEW, MemoryAction.TOMBSTONE}
    assert "stale" in decision.reasons
    assert "unprovenanced" in decision.reasons
    assert "unused" in decision.reasons


def test_evaluate_many_is_deterministic_by_record_id() -> None:
    reconciler = MemoryReconciler(
        MemoryQualityPolicy(half_life_s=100.0)
    )
    decisions = reconciler.evaluate_many(
        (_record("z"), _record("a")),
        now=100.0,
    )
    assert [decision.record_id for decision in decisions] == ["a", "z"]


def test_duplicate_records_fail_closed() -> None:
    reconciler = MemoryReconciler()
    with pytest.raises(ValueError, match="unique"):
        reconciler.evaluate_many((_record("a"), _record("a")), now=100.0)


def test_tombstone_contains_canonical_and_all_derived_targets() -> None:
    ledger = TombstoneLedger()
    tombstone = ledger.issue(
        _record(),
        issued_at=100.0,
        reason="privacy-delete",
    )

    assert tombstone.targets == (
        "memory:m1",
        "embedding:m1",
        "index:m1",
    )
    assert tombstone.complete is False
    assert set(tombstone.pending) == set(tombstone.targets)


def test_tombstone_does_not_complete_until_every_projection_acknowledges() -> None:
    ledger = TombstoneLedger()
    tombstone = ledger.issue(
        _record(),
        issued_at=100.0,
        reason="privacy-delete",
    )

    current = ledger.acknowledge(tombstone.tombstone_id, "memory:m1")
    assert current.complete is False
    current = ledger.acknowledge(tombstone.tombstone_id, "embedding:m1")
    assert current.complete is False
    current = ledger.acknowledge(tombstone.tombstone_id, "index:m1")
    assert current.complete is True
    assert current.pending == ()
    assert ledger.incomplete() == ()


def test_tombstone_reissue_is_idempotent_for_record() -> None:
    ledger = TombstoneLedger()
    first = ledger.issue(_record(), issued_at=100.0, reason="delete")
    second = ledger.issue(_record(), issued_at=200.0, reason="delete-again")
    assert second == first


def test_tombstone_unknown_target_fails_closed() -> None:
    ledger = TombstoneLedger()
    tombstone = ledger.issue(_record(), issued_at=100.0, reason="delete")
    with pytest.raises(ValueError, match="not part"):
        ledger.acknowledge(tombstone.tombstone_id, "backup:unknown")


def test_tombstone_checkpoint_round_trip_preserves_acknowledgements() -> None:
    ledger = TombstoneLedger()
    tombstone = ledger.issue(_record(), issued_at=100.0, reason="delete")
    ledger.acknowledge(tombstone.tombstone_id, "memory:m1")
    state = ledger.snapshot()

    restored = TombstoneLedger.from_snapshot(copy.deepcopy(state))

    assert restored.snapshot() == state
    restored_row = restored.get(tombstone.tombstone_id)
    assert restored_row is not None
    assert restored_row.acknowledged == ("memory:m1",)
    assert restored_row.complete is False


@pytest.mark.parametrize(
    "field,value",
    (
        ("confidence", 1.1),
        ("importance", -0.1),
        ("access_count", -1),
        ("provenance_count", -1),
        ("contradiction_count", -1),
    ),
)
def test_memory_record_rejects_invalid_quality_state(field, value) -> None:
    kwargs = {
        "record_id": "m",
        "memory_class": "semantic",
        "created_at": 0.0,
        "updated_at": 0.0,
        "last_accessed_at": 0.0,
        "confidence": 0.5,
        "importance": 0.5,
        "access_count": 0,
        "provenance_count": 0,
        "contradiction_count": 0,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        MemoryRecord(**kwargs)
