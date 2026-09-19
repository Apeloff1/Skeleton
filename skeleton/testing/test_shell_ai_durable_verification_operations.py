"""Operations and retention fast-path contracts for signed durable verification."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_operations import (
    DurableChainOperationalState,
    DurableEvidenceOperationsInspector,
    DurableOperationsPolicy,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionError,
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
    DurableVerificationPolicy,
    DurableVerificationStatus,
)
from skeleton.shells.ai.durable_verification_health import (
    DurableChainVerificationHealth,
    DurableVerificationFleetGuard,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def append_events(
    chain: DistributedAIDecisionJournal,
    count: int,
    *,
    start: int = 0,
):
    values = []
    for index in range(start, start + count):
        values.append(
            chain.append(
                "ops.verified",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(values)


class CountingCheckpointableChain:
    """Expose both checkpoint and cursor protocols while counting expensive paths."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0
        self.verify_root_calls = 0
        self.ancestor_calls = 0
        self.snapshot_at_calls = 0
        self.segment_calls = 0

    @property
    def max_events(self):
        return self.delegate.max_events

    def head(self):
        return self.delegate.head()

    def verify(self):
        self.verify_calls += 1
        return self.delegate.verify()

    def verify_root(self, root_hash):
        self.verify_root_calls += 1
        return self.delegate.verify_root(
            root_hash
        )

    def root_is_ancestor(self, root_hash):
        self.ancestor_calls += 1
        return self.delegate.root_is_ancestor(
            root_hash
        )

    def snapshot_at(self, root_hash):
        self.snapshot_at_calls += 1
        return self.delegate.snapshot_at(
            root_hash
        )

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        self.segment_calls += 1
        return self.delegate.snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )

    def root_hash(self):
        return self.delegate.root_hash()

    def length(self):
        return self.delegate.length()


def fixture(
    *,
    capacity=100,
    target_utilization=0.8,
    verification_policy=None,
):
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=capacity,
        clock=lambda: 10.0,
    )
    chain = CountingCheckpointableChain(
        raw
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        ArtifactSigner(
            "checkpoints",
            b"c" * 32,
            clock=lambda: 100.0,
        ),
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=target_utilization,
            warning_utilization=max(
                target_utilization,
                0.85,
            ),
            critical_utilization=0.95,
            max_protected_roots=16,
        ),
    )
    cursor_store = (
        DurableVerificationCursorStore(
            backend,
            ArtifactSigner(
                "cursor",
                b"v" * 32,
                clock=lambda: 100.0,
            ),
            namespace="cursors",
        )
    )
    incremental = DurableIncrementalVerifier(
        cursor_store,
        verification_policy,
        clock=lambda: 100.0,
    )
    guard = DurableVerificationFleetGuard(
        incremental
    )
    inspector = DurableEvidenceOperationsInspector(
        checkpoints,
        retention,
        verification_guard=guard,
    )
    return (
        backend,
        raw,
        chain,
        checkpoints,
        retention,
        guard,
        inspector,
    )


def test_retention_accepts_exact_signed_current_head():
    (
        _,
        _,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(chain.delegate, 3)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    before = chain.verify_calls
    plan = retention.plan(
        "journal",
        chain,
        verified_head=health,
    )
    assert plan.current_sequence == 3
    assert chain.verify_calls == before


def test_retention_rejects_unhealthy_verified_head():
    (
        _,
        _,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(chain.delegate, 1)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    unhealthy = replace(
        health,
        verified=False,
    )
    with pytest.raises(
        DurableRetentionError,
        match="not healthy",
    ):
        retention.plan(
            "journal",
            chain,
            verified_head=unhealthy,
        )


def test_retention_rejects_verified_head_chain_id_mismatch():
    (
        _,
        _,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(chain.delegate, 1)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    with pytest.raises(
        DurableRetentionError,
        match="chain_id mismatch",
    ):
        retention.plan(
            "other",
            chain,
            verified_head=health,
        )


def test_retention_rejects_verified_head_sequence_mismatch():
    (
        _,
        _,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(chain.delegate, 1)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    mismatched = replace(
        health,
        current_sequence=0,
    )
    with pytest.raises(
        DurableRetentionError,
        match="differs from live head",
    ):
        retention.plan(
            "journal",
            chain,
            verified_head=mismatched,
        )


def test_retention_rejects_verified_head_root_mismatch():
    (
        _,
        _,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(chain.delegate, 1)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    mismatched = replace(
        health,
        current_root=fp("other"),
    )
    with pytest.raises(
        DurableRetentionError,
        match="differs from live head",
    ):
        retention.plan(
            "journal",
            chain,
            verified_head=mismatched,
        )


def test_retention_rejects_wrong_verified_head_type():
    (
        _,
        _,
        chain,
        _,
        retention,
        _,
        _,
    ) = fixture()
    with pytest.raises(
        TypeError,
        match="DurableChainVerificationHealth",
    ):
        retention.plan(
            "journal",
            chain,
            verified_head=object(),
        )


def test_retention_without_attestation_still_full_verifies():
    (
        _,
        _,
        chain,
        _,
        retention,
        _,
        _,
    ) = fixture()
    append_events(chain.delegate, 2)
    assert chain.verify_calls == 0
    retention.plan(
        "journal",
        chain,
    )
    assert chain.verify_calls == 1


def test_operations_with_current_cursor_skip_full_verify():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 3)
    guard.require(
        (("journal", chain),)
    )
    full_calls = chain.verify_calls
    report = inspector.inspect(
        (("journal", chain),)
    )
    assert report.allowed
    assert chain.verify_calls == full_calls
    item = report.chains[0]
    assert item.chain_valid
    assert item.verification_health is not None
    assert item.verification_health.ok
    assert (
        item.verification_health.status
        is DurableVerificationStatus.CURRENT
    )


def test_operations_repeated_inspection_keeps_full_replay_flat():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 3)
    guard.require(
        (("journal", chain),)
    )
    full_calls = chain.verify_calls
    for _ in range(10):
        report = inspector.require(
            (("journal", chain),)
        )
        assert report.allowed
    assert chain.verify_calls == full_calls


def test_operations_after_incremental_cursor_advance_skip_full_replay():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 2)
    guard.require(
        (("journal", chain),)
    )
    full_calls = chain.verify_calls
    append_events(
        chain.delegate,
        2,
        start=2,
    )
    guard.require(
        (("journal", chain),)
    )
    assert chain.segment_calls == 1
    report = inspector.require(
        (("journal", chain),)
    )
    assert report.allowed
    assert chain.verify_calls == full_calls
    assert (
        report.chains[0]
        .verification_health.current_sequence
        == 4
    )


def test_operations_stale_cursor_fails_closed():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 2)
    guard.require(
        (("journal", chain),)
    )
    append_events(
        chain.delegate,
        1,
        start=2,
    )
    report = inspector.inspect(
        (("journal", chain),)
    )
    assert not report.allowed
    item = report.chains[0]
    assert not item.chain_valid
    assert item.state is (
        DurableChainOperationalState.INVALID
    )
    assert any(
        finding.code
        == "durable_verification.cursor_not_current"
        for finding in item.findings
    )


def test_operations_stale_cursor_does_not_trust_retention_head():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 2)
    guard.require(
        (("journal", chain),)
    )
    full_calls = chain.verify_calls
    append_events(
        chain.delegate,
        1,
        start=2,
    )
    report = inspector.inspect(
        (("journal", chain),)
    )
    assert not report.allowed
    # Since the signed head was stale, retention does not receive it and falls
    # back to its full integrity check rather than trusting stale metadata.
    assert chain.verify_calls == full_calls + 1


def test_operations_constructor_rejects_wrong_verification_guard():
    (
        _,
        _,
        _,
        checkpoints,
        retention,
        _,
        _,
    ) = fixture()
    with pytest.raises(
        TypeError,
        match="verification_guard",
    ):
        DurableEvidenceOperationsInspector(
            checkpoints,
            retention,
            verification_guard=object(),
        )


def test_operations_report_serializes_verification_health():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 1)
    guard.require(
        (("journal", chain),)
    )
    report = inspector.require(
        (("journal", chain),)
    )
    data = report.to_dict()
    health = (
        data["chains"][0]
        ["verification_health"]
    )
    assert health is not None
    assert health["status"] == "current"
    assert health["verified"] is True


def test_operations_report_digest_binds_verification_health():
    (
        _,
        _,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    append_events(chain.delegate, 1)
    guard.require(
        (("journal", chain),)
    )
    first = inspector.require(
        (("journal", chain),)
    )
    append_events(
        chain.delegate,
        1,
        start=1,
    )
    guard.require(
        (("journal", chain),)
    )
    second = inspector.require(
        (("journal", chain),)
    )
    assert first.digest != second.digest
    assert (
        first.chains[0]
        .verification_health.cursor_digest
        != second.chains[0]
        .verification_health.cursor_digest
    )


def test_protected_root_still_uses_historical_ancestry_checks():
    (
        _,
        raw,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture()
    events = append_events(raw, 4)
    guard.require(
        (("journal", chain),)
    )
    before_ancestor = chain.ancestor_calls
    before_snapshot = chain.snapshot_at_calls
    report = inspector.require(
        (("journal", chain),),
        protected_roots={
            "journal": (
                events[1].event_hash,
            ),
        },
    )
    assert report.allowed
    assert chain.ancestor_calls > before_ancestor
    assert chain.snapshot_at_calls > before_snapshot


def test_signed_checkpoint_still_uses_historical_verification():
    (
        _,
        raw,
        chain,
        checkpoints,
        _,
        guard,
        inspector,
    ) = fixture(
        target_utilization=0.3,
    )
    append_events(raw, 4)
    checkpoint = checkpoints.publish(
        "journal",
        chain,
    )
    assert checkpoint.checkpoint.sequence == 4
    guard.require(
        (("journal", chain),)
    )
    append_events(
        raw,
        2,
        start=4,
    )
    guard.require(
        (("journal", chain),)
    )
    before = (
        chain.verify_root_calls
        + chain.ancestor_calls
        + chain.snapshot_at_calls
    )
    report = inspector.inspect(
        (("journal", chain),)
    )
    assert report.allowed
    after = (
        chain.verify_root_calls
        + chain.ancestor_calls
        + chain.snapshot_at_calls
    )
    assert after > before
    assert (
        report.chains[0]
        .latest_checkpoint_digest
        == checkpoint.checkpoint.digest
    )


def test_verified_head_does_not_authorize_local_deletion():
    (
        _,
        raw,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(raw, 5)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    plan = retention.plan(
        "journal",
        chain,
        verified_head=health,
    )
    assert not plan.local_deletion_safe
    assert any(
        "deletion remains unsafe"
        in reason
        for reason in plan.reasons
    )


def test_cursor_health_cannot_bypass_capacity_critical_policy():
    (
        _,
        raw,
        chain,
        _,
        _,
        guard,
        inspector,
    ) = fixture(
        capacity=10,
        target_utilization=0.5,
    )
    append_events(raw, 10)
    guard.require(
        (("journal", chain),)
    )
    report = inspector.inspect(
        (("journal", chain),)
    )
    assert not report.allowed
    assert report.chains[0].state is (
        DurableChainOperationalState.INVALID
    )
    assert any(
        "capacity_critical"
        in finding.code
        for finding in report.chains[0].findings
    )


def test_cursor_health_cannot_bypass_checkpoint_requirement_policy():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=10,
        clock=lambda: 10.0,
    )
    chain = CountingCheckpointableChain(
        raw
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        ArtifactSigner(
            "checkpoints",
            b"c" * 32,
        ),
        namespace="checkpoints",
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=2,
            target_utilization=0.5,
            warning_utilization=0.6,
            critical_utilization=0.95,
        ),
    )
    cursor_store = DurableVerificationCursorStore(
        backend,
        ArtifactSigner(
            "cursor",
            b"v" * 32,
        ),
        namespace="cursors",
    )
    guard = DurableVerificationFleetGuard(
        DurableIncrementalVerifier(
            cursor_store
        )
    )
    inspector = DurableEvidenceOperationsInspector(
        checkpoints,
        retention,
        verification_guard=guard,
        policy=DurableOperationsPolicy(
            require_checkpoint_above_warning=True,
        ),
    )
    append_events(raw, 7)
    guard.require(
        (("journal", chain),)
    )
    report = inspector.inspect(
        (("journal", chain),)
    )
    assert not report.allowed
    assert any(
        finding.code
        == "durable_checkpoint.required_above_warning"
        for finding in report.chains[0].findings
    )


class FullVerifyBombChain(
    CountingCheckpointableChain
):
    def verify(self):
        self.verify_calls += 1
        raise AssertionError(
            "unexpected full-chain replay"
        )


def test_operations_can_run_with_full_verify_bomb_after_cursor_bootstrap():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
        clock=lambda: 10.0,
    )
    append_events(raw, 3)
    normal = CountingCheckpointableChain(
        raw
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        ArtifactSigner(
            "checkpoint",
            b"c" * 32,
        ),
        namespace="checkpoints",
    )
    retention = DurableRetentionPlanner(
        checkpoints,
    )
    store = DurableVerificationCursorStore(
        backend,
        ArtifactSigner(
            "cursor",
            b"v" * 32,
        ),
        namespace="cursors",
    )
    guard = DurableVerificationFleetGuard(
        DurableIncrementalVerifier(store)
    )
    guard.require(
        (("journal", normal),)
    )

    bomb = FullVerifyBombChain(raw)
    inspector = DurableEvidenceOperationsInspector(
        checkpoints,
        retention,
        verification_guard=guard,
    )
    report = inspector.require(
        (("journal", bomb),)
    )
    assert report.allowed
    assert bomb.verify_calls == 0


def test_tail_advance_then_operations_with_bomb_still_avoids_full_replay():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
        clock=lambda: 10.0,
    )
    append_events(raw, 2)
    normal = CountingCheckpointableChain(
        raw
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        ArtifactSigner(
            "checkpoint",
            b"c" * 32,
        ),
        namespace="checkpoints",
    )
    retention = DurableRetentionPlanner(
        checkpoints,
    )
    store = DurableVerificationCursorStore(
        backend,
        ArtifactSigner(
            "cursor",
            b"v" * 32,
        ),
        namespace="cursors",
    )
    guard = DurableVerificationFleetGuard(
        DurableIncrementalVerifier(store)
    )
    guard.require(
        (("journal", normal),)
    )
    append_events(
        raw,
        2,
        start=2,
    )
    guard.require(
        (("journal", normal),)
    )

    bomb = FullVerifyBombChain(raw)
    inspector = DurableEvidenceOperationsInspector(
        checkpoints,
        retention,
        verification_guard=guard,
    )
    report = inspector.require(
        (("journal", bomb),)
    )
    assert report.allowed
    assert bomb.verify_calls == 0


def test_verified_health_is_head_specific_not_chain_object_specific():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
        clock=lambda: 10.0,
    )
    append_events(raw, 2)
    first_view = CountingCheckpointableChain(
        raw
    )
    second_view = CountingCheckpointableChain(
        raw
    )
    store = DurableVerificationCursorStore(
        backend,
        ArtifactSigner(
            "cursor",
            b"v" * 32,
        ),
        namespace="cursors",
    )
    guard = DurableVerificationFleetGuard(
        DurableIncrementalVerifier(store)
    )
    guard.require(
        (("journal", first_view),)
    )
    report = guard.inspect(
        (("journal", second_view),)
    )
    assert report.allowed
    assert report.chains[0].ok
    assert second_view.verify_calls == 0


def test_verified_head_type_is_exposed_in_plan_contract():
    (
        _,
        raw,
        chain,
        _,
        retention,
        guard,
        _,
    ) = fixture()
    append_events(raw, 1)
    guard.require(
        (("journal", chain),)
    )
    health = guard.inspect(
        (("journal", chain),)
    ).chains[0]
    assert isinstance(
        health,
        DurableChainVerificationHealth,
    )
    plan = retention.plan(
        "journal",
        chain,
        verified_head=health,
    )
    assert plan.current_root == health.current_root


def test_unverified_health_with_zero_errors_still_rejected():
    health = DurableChainVerificationHealth(
        "journal",
        DurableVerificationStatus.TAIL_PENDING,
        False,
        2,
        fp("root"),
        1,
        fp("cursor-root"),
        fp("cursor"),
        1,
        1.0,
        1,
        False,
        (),
    )
    assert not health.ok
