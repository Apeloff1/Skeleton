"""Memory reconciliation must be deterministic and deletion must propagate completely."""

import copy

import pytest

from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryConflictCandidate,
    MemoryConflictLedger,
    MemoryConflictResolution,
    MemoryConflictResolver,
    MemoryGCDisposition,
    MemoryGCPlanner,
    MemoryQualityPolicy,
    MemoryReachability,
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



def _candidate(
    record_id: str,
    payload: str,
    *,
    scope: str = "tenant-a:user-a:project-a",
    claim: str = "favorite-language",
    confidence: float = 0.8,
    provenance_count: int = 2,
    updated_at: float = 100.0,
) -> MemoryConflictCandidate:
    import hashlib

    return MemoryConflictCandidate(
        record_id=record_id,
        scope_key=scope,
        claim_key=claim,
        payload_digest=hashlib.sha256(payload.encode()).hexdigest(),
        confidence=confidence,
        provenance_count=provenance_count,
        updated_at=updated_at,
    )


def test_conflict_builder_rejects_cross_scope_candidates() -> None:
    resolver = MemoryConflictResolver()
    with pytest.raises(ValueError, match="cross memory scopes"):
        resolver.build(
            (
                _candidate("a", "python", scope="tenant-a:user-a"),
                _candidate("b", "rust", scope="tenant-a:user-b"),
            ),
            created_at=100.0,
        )


def test_conflict_builder_requires_divergent_payloads() -> None:
    resolver = MemoryConflictResolver()
    with pytest.raises(ValueError, match="divergent payload"):
        resolver.build(
            (
                _candidate("a", "same"),
                _candidate("b", "same"),
            ),
            created_at=100.0,
        )


def test_ambiguous_conflict_remains_explicitly_unresolved() -> None:
    resolver = MemoryConflictResolver()
    conflict = resolver.build(
        (
            _candidate("a", "python", confidence=0.8, provenance_count=2),
            _candidate("b", "rust", confidence=0.75, provenance_count=2),
        ),
        created_at=100.0,
    )

    resolved = resolver.resolve(conflict)

    assert resolved.resolution is MemoryConflictResolution.UNRESOLVED
    assert resolved.winner_id is None
    assert resolved.superseded_ids == ()


def test_conflict_resolves_only_with_confidence_and_provenance_dominance() -> None:
    resolver = MemoryConflictResolver()
    conflict = resolver.build(
        (
            _candidate("winner", "python", confidence=0.95, provenance_count=5),
            _candidate("loser", "rust", confidence=0.60, provenance_count=2),
        ),
        created_at=100.0,
    )

    resolved = resolver.resolve(conflict)

    assert resolved.resolution is MemoryConflictResolution.SUPERSEDE
    assert resolved.winner_id == "winner"
    assert resolved.superseded_ids == ("loser",)
    assert resolved.reason == "confidence-and-provenance-dominance"


def test_quality_review_blocks_automatic_conflict_resolution() -> None:
    resolver = MemoryConflictResolver()
    conflict = resolver.build(
        (
            _candidate("winner", "python", confidence=0.95, provenance_count=5),
            _candidate("loser", "rust", confidence=0.60, provenance_count=2),
        ),
        created_at=100.0,
    )

    resolved = resolver.resolve(
        conflict,
        quality_actions={
            "winner": MemoryAction.RETAIN,
            "loser": MemoryAction.REVIEW,
        },
    )

    assert resolved.resolution is MemoryConflictResolution.UNRESOLVED


def test_quality_unique_retain_can_supersede_tombstoned_alternatives() -> None:
    resolver = MemoryConflictResolver()
    conflict = resolver.build(
        (
            _candidate("winner", "python", confidence=0.6, provenance_count=1),
            _candidate("loser", "rust", confidence=0.9, provenance_count=5),
        ),
        created_at=100.0,
    )

    resolved = resolver.resolve(
        conflict,
        quality_actions={
            "winner": MemoryAction.RETAIN,
            "loser": MemoryAction.TOMBSTONE,
        },
    )

    assert resolved.resolution is MemoryConflictResolution.SUPERSEDE
    assert resolved.winner_id == "winner"
    assert resolved.reason == "quality-policy-unique-retain"


def test_keep_both_requires_explicit_reason() -> None:
    resolver = MemoryConflictResolver()
    conflict = resolver.build(
        (_candidate("a", "python"), _candidate("b", "rust")),
        created_at=100.0,
    )

    with pytest.raises(ValueError, match="requires a reason"):
        resolver.keep_both(conflict, reason="")

    resolved = resolver.keep_both(
        conflict,
        reason="both are scoped temporal observations",
    )
    assert resolved.resolution is MemoryConflictResolution.KEEP_BOTH
    assert resolved.reason == "both are scoped temporal observations"


def test_conflict_ledger_refuses_to_replace_unresolved_claim() -> None:
    resolver = MemoryConflictResolver()
    ledger = MemoryConflictLedger()
    first = resolver.build(
        (_candidate("a", "python"), _candidate("b", "rust")),
        created_at=100.0,
    )
    second = resolver.build(
        (_candidate("a", "python"), _candidate("c", "go")),
        created_at=101.0,
    )
    ledger.open(first)

    with pytest.raises(ValueError, match="cannot replace unresolved"):
        ledger.open(second)


def test_conflict_ledger_resolution_and_snapshot_round_trip() -> None:
    resolver = MemoryConflictResolver()
    ledger = MemoryConflictLedger()
    conflict = resolver.build(
        (
            _candidate("a", "python", confidence=0.95, provenance_count=5),
            _candidate("b", "rust", confidence=0.5, provenance_count=1),
        ),
        created_at=100.0,
    )
    ledger.open(conflict)
    resolved = resolver.resolve(conflict)
    ledger.resolve(resolved)

    snapshot = ledger.snapshot()
    restored = MemoryConflictLedger.from_snapshot(copy.deepcopy(snapshot))

    assert restored.snapshot() == snapshot
    assert restored.unresolved() == ()
    assert restored.get(conflict.conflict_id) == resolved


def test_gc_tombstones_only_unprotected_low_quality_memory() -> None:
    planner = MemoryGCPlanner(
        MemoryReconciler(
            MemoryQualityPolicy(
                half_life_s=1.0,
                retain_threshold=0.8,
                tombstone_threshold=0.4,
                hard_contradiction_limit=1,
            )
        )
    )
    poor = _record(
        "poor",
        confidence=0.1,
        importance=0.1,
        access_count=0,
        provenance_count=0,
        contradiction_count=1,
        last_accessed_at=0.0,
    )

    plan = planner.plan((poor,), now=100.0)

    assert plan.tombstone_ids == ("poor",)
    assert plan.review_ids == ()
    assert plan.entries[0].disposition is MemoryGCDisposition.TOMBSTONE


@pytest.mark.parametrize(
    "reachability,reason",
    (
        (MemoryReachability(record_id="poor", roots=("project:active",)), "reachable-from-root"),
        (MemoryReachability(record_id="poor", legal_hold=True), "legal-hold"),
        (MemoryReachability(record_id="poor", audit_required=True), "audit-required"),
        (
            MemoryReachability(record_id="poor", retention_until=200.0),
            "retention-window-active",
        ),
    ),
)
def test_gc_protections_block_tombstone(reachability, reason) -> None:
    planner = MemoryGCPlanner(
        MemoryReconciler(
            MemoryQualityPolicy(
                half_life_s=1.0,
                retain_threshold=0.8,
                tombstone_threshold=0.4,
                hard_contradiction_limit=1,
            )
        )
    )
    poor = _record(
        "poor",
        confidence=0.1,
        importance=0.1,
        access_count=0,
        provenance_count=0,
        contradiction_count=1,
        last_accessed_at=0.0,
    )

    plan = planner.plan(
        (poor,),
        reachability=(reachability,),
        now=100.0,
    )

    assert plan.tombstone_ids == ()
    assert plan.review_ids == ("poor",)
    assert reason in plan.entries[0].reasons
    assert "deletion-blocked" in plan.entries[0].reasons


def test_expired_retention_window_no_longer_blocks_gc() -> None:
    planner = MemoryGCPlanner(
        MemoryReconciler(
            MemoryQualityPolicy(
                half_life_s=1.0,
                retain_threshold=0.8,
                tombstone_threshold=0.4,
                hard_contradiction_limit=1,
            )
        )
    )
    poor = _record(
        "poor",
        confidence=0.1,
        importance=0.1,
        access_count=0,
        provenance_count=0,
        contradiction_count=1,
        last_accessed_at=0.0,
    )

    plan = planner.plan(
        (poor,),
        reachability=(
            MemoryReachability(record_id="poor", retention_until=99.0),
        ),
        now=100.0,
    )

    assert plan.tombstone_ids == ("poor",)


def test_gc_rejects_unknown_reachability_record() -> None:
    with pytest.raises(ValueError, match="unknown memory"):
        MemoryGCPlanner().plan(
            (_record("known"),),
            reachability=(MemoryReachability(record_id="unknown"),),
            now=100.0,
        )


def test_gc_plan_is_deterministic_by_record_id() -> None:
    plan = MemoryGCPlanner().plan(
        (_record("z"), _record("a")),
        now=100.0,
    )
    assert [entry.record_id for entry in plan.entries] == ["a", "z"]
