"""Signed durable checkpoint and non-destructive retention tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpoint,
    DurableChainCheckpointStore,
    DurableCheckpointError,
    DurableCheckpointVerification,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionError,
    DurableRetentionPlan,
    DurableRetentionPlanner,
    DurableRetentionPolicy,
    DurableRetentionState,
    ProtectedHistoricalRoot,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def signer(
    *,
    clock=lambda: 100.0,
) -> ArtifactSigner:
    return ArtifactSigner(
        "checkpoint-key",
        b"k" * 32,
        clock=clock,
    )


def checkpoint_store(
    backend=None,
    *,
    clock=lambda: 100.0,
    namespace="checkpoints",
):
    backend = backend or InMemoryFencedStore()
    return (
        backend,
        DurableChainCheckpointStore(
            backend,
            signer(clock=clock),
            namespace=namespace,
            clock=clock,
        ),
    )


def journal(
    backend=None,
    *,
    namespace="journal",
    max_events=100,
):
    backend = backend or InMemoryFencedStore()
    return (
        backend,
        DistributedAIDecisionJournal(
            backend,
            namespace=namespace,
            max_events=max_events,
            clock=lambda: 10.0,
        ),
    )


def append_events(
    target: DistributedAIDecisionJournal,
    count: int,
    *,
    session_prefix="session",
):
    result = []
    for index in range(count):
        result.append(
            target.append(
                "test.event",
                session_id=f"{session_prefix}-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(result)


def receipt(
    index: int,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"correlation-{index}",
        fingerprint=fp(f"receipt:{index}"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def test_checkpoint_empty_journal_genesis():
    backend, target = journal()
    _, store = checkpoint_store(backend)
    item = store.publish(
        "journal",
        target,
    )
    assert item.checkpoint.sequence == 0
    assert item.checkpoint.root_hash == target.root_hash()
    assert item.checkpoint.previous_checkpoint_digest == ""
    assert store.verify()
    report = store.require(item, target)
    assert report.valid
    assert report.current_sequence == 0


def test_checkpoint_nonempty_journal():
    backend, target = journal()
    append_events(target, 3)
    _, store = checkpoint_store(backend)
    item = store.publish(
        "journal",
        target,
    )
    assert item.checkpoint.sequence == 3
    assert item.checkpoint.root_hash == target.root_hash()
    assert item.signature.artifact_type == (
        "durable-chain-checkpoint"
    )
    assert (
        item.signature.artifact_digest
        == item.checkpoint.digest
    )
    assert len(item.chain_node_hash) == 64
    assert store.verify()


def test_checkpoint_publish_same_head_is_idempotent():
    backend, target = journal()
    append_events(target, 2)
    _, store = checkpoint_store(backend)
    first = store.publish("journal", target)
    second = store.publish("journal", target)
    assert second == first
    assert store.length() == 1


def test_checkpoint_advance_links_previous_digest():
    backend, target = journal()
    append_events(target, 2)
    _, store = checkpoint_store(backend)
    first = store.publish("journal", target)
    append_events(target, 2)
    second = store.publish("journal", target)
    assert second.checkpoint.sequence == 4
    assert (
        second.checkpoint.previous_checkpoint_digest
        == first.checkpoint.digest
    )
    assert store.length() == 2
    assert store.verify()


def test_checkpoint_separate_chain_ids_have_independent_history():
    backend, first_chain = journal(
        namespace="journal-one"
    )
    _, second_chain = journal(
        backend,
        namespace="journal-two",
    )
    append_events(first_chain, 2)
    append_events(second_chain, 1)
    _, store = checkpoint_store(backend)
    first = store.publish(
        "journal-one",
        first_chain,
    )
    second = store.publish(
        "journal-two",
        second_chain,
    )
    assert first.checkpoint.previous_checkpoint_digest == ""
    assert second.checkpoint.previous_checkpoint_digest == ""
    assert len(store.for_chain("journal-one")) == 1
    assert len(store.for_chain("journal-two")) == 1
    assert store.verify()


def test_checkpoint_receipt_chain():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=20,
    )
    receipts.append(receipt(1))
    receipts.append(receipt(2))
    _, store = checkpoint_store(backend)
    item = store.publish(
        "receipts",
        receipts,
    )
    assert item.checkpoint.sequence == 2
    assert item.checkpoint.root_hash == receipts.root_hash()
    assert store.require(item, receipts).valid


def test_checkpoint_survives_fresh_store_reader():
    backend, target = journal()
    append_events(target, 4)
    _, first = checkpoint_store(
        backend,
        namespace="checkpoints",
    )
    item = first.publish(
        "journal",
        target,
    )
    second = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
    )
    loaded = second.latest("journal")
    assert loaded == item
    assert second.verify()
    assert second.require(loaded, target).valid


def test_checkpoint_remains_valid_after_chain_advances():
    backend, target = journal()
    append_events(target, 2)
    _, store = checkpoint_store(backend)
    item = store.publish(
        "journal",
        target,
    )
    old_root = item.checkpoint.root_hash
    append_events(target, 3)
    report = store.require(
        item,
        target,
    )
    assert report.valid
    assert report.root_is_ancestor
    assert report.current_sequence == 5
    assert report.current_root == target.root_hash()
    assert target.root_hash() != old_root


def test_checkpoint_latest_tracks_chain_specific_latest():
    backend, target = journal()
    append_events(target, 1)
    _, store = checkpoint_store(backend)
    first = store.publish(
        "journal",
        target,
    )
    append_events(target, 1)
    second = store.publish(
        "journal",
        target,
    )
    assert store.latest("journal") == second
    assert store.latest("missing") is None
    assert first != second


def test_checkpoint_invalid_chain_id():
    _, target = journal()
    _, store = checkpoint_store()
    with pytest.raises(ValueError, match="chain_id"):
        store.publish("", target)
    with pytest.raises(ValueError, match="chain_id"):
        store.for_chain("")
    with pytest.raises(ValueError, match="chain_id"):
        store.latest("")


class BadChain:
    def head(self):
        return type(
            "Head",
            (),
            {
                "sequence": 1,
                "root_hash": fp("bad"),
            },
        )()

    def verify(self):
        return False

    def verify_root(self, root_hash):
        return False

    def root_is_ancestor(self, root_hash):
        return False

    def snapshot_at(self, root_hash):
        return ()


def test_checkpoint_invalid_chain_is_rejected():
    _, store = checkpoint_store()
    with pytest.raises(
        DurableCheckpointError,
        match="invalid evidence chain",
    ):
        store.publish(
            "bad",
            BadChain(),
        )


def test_checkpoint_requires_checkpointable_surface():
    _, store = checkpoint_store()
    with pytest.raises(TypeError, match="checkpoint"):
        store.publish(
            "bad",
            object(),
        )


def test_checkpoint_registry_signature_tamper_detected():
    backend, target = journal()
    append_events(target, 1)
    _, store = checkpoint_store(backend)
    store.publish("journal", target)
    node = store._chain.snapshot()[0]
    record = backend.get(
        store._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    signature = dict(
        payload["signature"]
    )
    signature["signature"] = fp("tampered")
    payload["signature"] = signature
    backend.compare_and_swap(
        store._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload=payload,
        ),
    )
    assert not store.verify()


def test_checkpoint_registry_payload_tamper_detected():
    backend, target = journal()
    append_events(target, 1)
    _, store = checkpoint_store(backend)
    store.publish("journal", target)
    node = store._chain.snapshot()[0]
    record = backend.get(
        store._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    checkpoint = dict(
        payload["checkpoint"]
    )
    checkpoint["sequence"] = 999
    payload["checkpoint"] = checkpoint
    backend.compare_and_swap(
        store._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload=payload,
        ),
    )
    assert not store.verify()


def test_checkpoint_previous_digest_tamper_detected():
    backend, target = journal()
    append_events(target, 1)
    _, store = checkpoint_store(backend)
    store.publish("journal", target)
    append_events(target, 1)
    store.publish("journal", target)
    second = store._chain.snapshot()[1]
    record = backend.get(
        store._chain.namespace,
        f"node:{second.node_hash}",
    )
    payload = dict(second.payload)
    checkpoint = dict(
        payload["checkpoint"]
    )
    checkpoint[
        "previous_checkpoint_digest"
    ] = fp("wrong")
    payload["checkpoint"] = checkpoint
    backend.compare_and_swap(
        store._chain.namespace,
        f"node:{second.node_hash}",
        expected_revision=record.revision,
        value=replace(
            second,
            payload=payload,
        ),
    )
    assert not store.verify()


def test_checkpoint_inspect_requires_canonical_registry_membership():
    backend, target = journal()
    append_events(target, 1)
    _, store = checkpoint_store(backend)
    canonical = store.publish(
        "journal",
        target,
    )
    forged_checkpoint = replace(
        canonical.checkpoint,
        observed_at=canonical.checkpoint.observed_at + 1,
    )
    forged_signature = store.signer.sign(
        "durable-chain-checkpoint",
        forged_checkpoint.digest,
        metadata={
            "chain_id": "journal",
            "sequence": 1,
        },
    )
    forged = SignedDurableChainCheckpoint(
        forged_checkpoint,
        forged_signature,
        fp("not-committed"),
    )
    report = store.inspect(
        forged,
        target,
    )
    assert not report.valid
    assert any(
        "not committed" in reason
        for reason in report.reasons
    )


def test_checkpoint_require_rejects_noncanonical_item():
    backend, target = journal()
    append_events(target, 1)
    _, store = checkpoint_store(backend)
    canonical = store.publish("journal", target)
    forged = replace(
        canonical,
        chain_node_hash=fp("other"),
    )
    with pytest.raises(
        DurableCheckpointError,
        match="not committed",
    ):
        store.require(forged, target)


def test_checkpoint_dataclass_validation():
    with pytest.raises(ValueError):
        DurableChainCheckpoint(
            2,
            "chain",
            1,
            fp("root"),
            "",
            1.0,
        )
    with pytest.raises(ValueError):
        DurableChainCheckpoint(
            1,
            "",
            1,
            fp("root"),
            "",
            1.0,
        )
    with pytest.raises(ValueError):
        DurableChainCheckpoint(
            1,
            "chain",
            -1,
            fp("root"),
            "",
            1.0,
        )
    with pytest.raises(ValueError):
        DurableChainCheckpoint(
            1,
            "chain",
            1,
            "bad",
            "",
            1.0,
        )
    with pytest.raises(ValueError):
        DurableChainCheckpoint(
            1,
            "chain",
            1,
            fp("root"),
            "bad",
            1.0,
        )
    with pytest.raises(ValueError):
        DurableChainCheckpoint(
            1,
            "chain",
            1,
            fp("root"),
            "",
            -1.0,
        )


def test_checkpoint_digest_is_deterministic():
    item = DurableChainCheckpoint(
        1,
        "chain",
        3,
        fp("root"),
        fp("previous"),
        10.0,
    )
    same = DurableChainCheckpoint(
        1,
        "chain",
        3,
        fp("root"),
        fp("previous"),
        10.0,
    )
    assert item.digest == same.digest
    assert len(item.digest) == 64


@pytest.mark.parametrize(
    "max_checkpoints",
    [0, -1, True],
)
def test_checkpoint_store_capacity_validation(
    max_checkpoints,
):
    with pytest.raises(
        ValueError,
        match="max_checkpoints",
    ):
        DurableChainCheckpointStore(
            InMemoryFencedStore(),
            signer(),
            max_checkpoints=max_checkpoints,
        )


def test_checkpoint_store_namespace_validation():
    with pytest.raises(ValueError, match="namespace"):
        DurableChainCheckpointStore(
            InMemoryFencedStore(),
            signer(),
            namespace="",
        )


def test_checkpoint_store_signer_validation():
    with pytest.raises(TypeError, match="signer"):
        DurableChainCheckpointStore(
            InMemoryFencedStore(),
            object(),
        )


def test_checkpoint_store_clock_validation():
    with pytest.raises(TypeError, match="clock"):
        DurableChainCheckpointStore(
            InMemoryFencedStore(),
            signer(),
            clock=object(),
        )


def test_checkpoint_verification_to_dict():
    item = DurableCheckpointVerification(
        True,
        "chain",
        1,
        fp("root"),
        2,
        fp("current"),
        True,
        (),
    )
    data = item.to_dict()
    assert data["valid"] is True
    assert data["sequence"] == 1
    assert data["root_is_ancestor"] is True


def test_default_retention_policy_shape():
    policy = DurableRetentionPolicy()
    assert policy.minimum_live_tail == 1000
    assert policy.minimum_archive_batch == 250
    assert policy.target_utilization == 0.70
    assert policy.warning_utilization == 0.80
    assert policy.critical_utilization == 0.95
    assert policy.max_protected_roots == 256


@pytest.mark.parametrize(
    "field,value",
    [
        ("minimum_live_tail", -1),
        ("minimum_live_tail", True),
        ("minimum_archive_batch", -1),
        ("minimum_archive_batch", True),
        ("max_protected_roots", 0),
        ("max_protected_roots", True),
    ],
)
def test_retention_policy_integer_validation(field, value):
    values = dict(
        minimum_live_tail=10,
        minimum_archive_batch=2,
        max_protected_roots=10,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableRetentionPolicy(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_utilization", 0),
        ("target_utilization", 1.1),
        ("target_utilization", float("nan")),
        ("warning_utilization", 0),
        ("critical_utilization", 2),
    ],
)
def test_retention_policy_threshold_validation(field, value):
    values = dict(
        target_utilization=0.5,
        warning_utilization=0.7,
        critical_utilization=0.9,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableRetentionPolicy(**values)


def test_retention_policy_thresholds_must_be_monotonic():
    with pytest.raises(ValueError, match="monotonic"):
        DurableRetentionPolicy(
            target_utilization=0.8,
            warning_utilization=0.7,
            critical_utilization=0.9,
        )


def test_retention_policy_digest_stable():
    first = DurableRetentionPolicy(
        minimum_live_tail=10,
        minimum_archive_batch=2,
        target_utilization=0.5,
        warning_utilization=0.7,
        critical_utilization=0.9,
    )
    second = DurableRetentionPolicy(
        minimum_live_tail=10,
        minimum_archive_batch=2,
        target_utilization=0.5,
        warning_utilization=0.7,
        critical_utilization=0.9,
    )
    assert first.digest == second.digest


def planner_fixture(
    *,
    max_events=10,
    policy=None,
):
    backend, target = journal(
        max_events=max_events
    )
    _, store = checkpoint_store(backend)
    planner = DurableRetentionPlanner(
        store,
        policy,
    )
    return backend, target, store, planner


def test_retention_healthy_below_target():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.7,
            warning_utilization=0.8,
            critical_utilization=0.95,
        ),
    )
    append_events(target, 3)
    store.publish("journal", target)
    plan = planner.plan(
        "journal",
        target,
    )
    assert plan.state is DurableRetentionState.HEALTHY
    assert not plan.archive_recommended
    assert plan.archive_through_sequence == 0
    assert not plan.local_deletion_safe


def test_retention_requires_checkpoint_under_pressure():
    _, target, _, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 6)
    plan = planner.plan(
        "journal",
        target,
    )
    assert plan.state is (
        DurableRetentionState.CHECKPOINT_REQUIRED
    )
    assert not plan.archive_recommended
    assert any(
        "requires a signed" in reason
        for reason in plan.reasons
    )


def test_retention_recommends_archive_at_eligible_checkpoint():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 4)
    checkpoint = store.publish(
        "journal",
        target,
    )
    append_events(target, 2)
    plan = planner.plan(
        "journal",
        target,
    )
    assert plan.state is (
        DurableRetentionState.ARCHIVE_RECOMMENDED
    )
    assert plan.archive_recommended
    assert plan.archive_through_sequence == 4
    assert (
        plan.archive_through_root
        == checkpoint.checkpoint.root_hash
    )
    assert plan.estimated_live_after_archive == 2
    assert not plan.local_deletion_safe


def test_retention_does_not_archive_checkpoint_inside_live_tail():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=3,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 5)
    store.publish("journal", target)
    append_events(target, 1)
    plan = planner.plan(
        "journal",
        target,
    )
    assert plan.archive_through_sequence == 0
    assert plan.state is (
        DurableRetentionState.CHECKPOINT_REQUIRED
    )


def test_retention_uses_latest_eligible_checkpoint():
    _, target, store, planner = planner_fixture(
        max_events=20,
        policy=DurableRetentionPolicy(
            minimum_live_tail=3,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 4)
    first = store.publish("journal", target)
    append_events(target, 4)
    second = store.publish("journal", target)
    append_events(target, 4)
    plan = planner.plan(
        "journal",
        target,
    )
    assert second.checkpoint.sequence == 8
    assert plan.archive_through_sequence == 8
    assert (
        plan.archive_through_root
        == second.checkpoint.root_hash
    )
    assert (
        plan.archive_through_root
        != first.checkpoint.root_hash
    )


def test_retention_respects_minimum_archive_batch():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=5,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 4)
    store.publish("journal", target)
    append_events(target, 2)
    plan = planner.plan(
        "journal",
        target,
    )
    assert not plan.archive_recommended
    assert plan.archive_through_sequence == 0
    assert any(
        "below minimum archive batch" in reason
        for reason in plan.reasons
    )


def test_retention_critical_state_at_capacity_pressure():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 7)
    store.publish("journal", target)
    append_events(target, 2)
    plan = planner.plan(
        "journal",
        target,
    )
    assert plan.state is (
        DurableRetentionState.CAPACITY_CRITICAL
    )
    assert plan.utilization == 0.9
    assert any(
        "critical" in reason
        for reason in plan.reasons
    )


def test_retention_warning_reason_without_archive():
    _, target, _, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=10,
            minimum_archive_batch=1,
            target_utilization=0.9,
            warning_utilization=0.7,
            critical_utilization=0.95,
        ),
    )
    append_events(target, 8)
    plan = planner.plan(
        "journal",
        target,
    )
    assert plan.state is DurableRetentionState.HEALTHY
    assert any(
        "warning threshold" in reason
        for reason in plan.reasons
    )


def test_retention_capacity_can_be_explicit():
    backend, target = journal(
        max_events=100
    )
    _, store = checkpoint_store(backend)
    planner = DurableRetentionPlanner(
        store,
        DurableRetentionPolicy(
            minimum_live_tail=1,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 5)
    plan = planner.plan(
        "journal",
        target,
        capacity=10,
    )
    assert plan.capacity == 10
    assert plan.utilization == 0.5


@pytest.mark.parametrize(
    "capacity",
    [0, -1, True],
)
def test_retention_explicit_capacity_validation(capacity):
    _, target, _, planner = planner_fixture()
    with pytest.raises(ValueError, match="capacity"):
        planner.plan(
            "journal",
            target,
            capacity=capacity,
        )


def test_retention_protected_root_is_reported():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    events = append_events(target, 4)
    protected = events[1].event_hash
    store.publish("journal", target)
    append_events(target, 2)
    plan = planner.plan(
        "journal",
        target,
        protected_roots=(protected,),
    )
    assert plan.protected_roots == (
        ProtectedHistoricalRoot(
            protected,
            2,
        ),
    )


def test_retention_rejects_uncommitted_protected_root():
    _, target, _, planner = planner_fixture()
    append_events(target, 2)
    with pytest.raises(
        DurableRetentionError,
        match="committed ancestor",
    ):
        planner.plan(
            "journal",
            target,
            protected_roots=(fp("missing"),),
        )


def test_retention_rejects_duplicate_protected_root():
    _, target, _, planner = planner_fixture()
    events = append_events(target, 2)
    root = events[0].event_hash
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        planner.plan(
            "journal",
            target,
            protected_roots=(root, root),
        )


def test_retention_protected_root_bound():
    _, target, _, planner = planner_fixture(
        policy=DurableRetentionPolicy(
            max_protected_roots=1,
        )
    )
    events = append_events(target, 2)
    with pytest.raises(
        ValueError,
        match="bound",
    ):
        planner.plan(
            "journal",
            target,
            protected_roots=(
                events[0].event_hash,
                events[1].event_hash,
            ),
        )


def test_retention_invalid_chain_is_rejected():
    _, store = checkpoint_store()
    planner = DurableRetentionPlanner(
        store
    )
    with pytest.raises(
        DurableRetentionError,
        match="invalid chain",
    ):
        planner.plan(
            "bad",
            BadChain(),
            capacity=10,
        )


def test_retention_wrong_chain_surface_rejected():
    _, store = checkpoint_store()
    planner = DurableRetentionPlanner(
        store
    )
    with pytest.raises(TypeError, match="retention"):
        planner.plan(
            "bad",
            object(),
            capacity=10,
        )


def test_retention_planner_requires_checkpoint_store():
    with pytest.raises(TypeError, match="checkpoints"):
        DurableRetentionPlanner(object())


def test_retention_plan_never_claims_local_deletion_safe():
    _, target, store, planner = planner_fixture(
        max_events=10,
        policy=DurableRetentionPolicy(
            minimum_live_tail=1,
            minimum_archive_batch=1,
            target_utilization=0.2,
            warning_utilization=0.5,
            critical_utilization=0.9,
        ),
    )
    append_events(target, 5)
    store.publish("journal", target)
    append_events(target, 1)
    plan = planner.plan("journal", target)
    assert plan.archive_recommended
    assert plan.local_deletion_safe is False
    assert any(
        "deletion remains unsafe" in reason
        for reason in plan.reasons
    )


def test_retention_plan_capacity_properties():
    plan = DurableRetentionPlan(
        "chain",
        DurableRetentionState.ARCHIVE_RECOMMENDED,
        fp("policy"),
        8,
        fp("current"),
        10,
        0.8,
        fp("checkpoint"),
        5,
        fp("root-five"),
        5,
        fp("root-five"),
        5,
        3,
        (),
        False,
        ("archive",),
    )
    assert plan.capacity_remaining == 2
    assert (
        plan.estimated_capacity_remaining_after_archive
        == 7
    )
    assert plan.archive_recommended


def test_retention_plan_digest_stable():
    values = dict(
        chain_id="chain",
        state=DurableRetentionState.HEALTHY,
        policy_digest=fp("policy"),
        current_sequence=1,
        current_root=fp("current"),
        capacity=10,
        utilization=0.1,
        checkpoint_digest="",
        checkpoint_sequence=0,
        checkpoint_root="",
        archive_through_sequence=0,
        archive_through_root="",
        archive_node_count=0,
        estimated_live_after_archive=1,
        protected_roots=(),
        local_deletion_safe=False,
        reasons=("safe",),
    )
    first = DurableRetentionPlan(**values)
    second = DurableRetentionPlan(**values)
    assert first.digest == second.digest
    assert first.to_dict()["digest"] == first.digest


def test_retention_plan_rejects_local_deletion_safe_true():
    with pytest.raises(ValueError, match="not supported"):
        DurableRetentionPlan(
            "chain",
            DurableRetentionState.HEALTHY,
            fp("policy"),
            0,
            fp("root"),
            10,
            0.0,
            "",
            0,
            "",
            0,
            "",
            0,
            0,
            (),
            True,
            (),
        )


def test_protected_root_validation():
    item = ProtectedHistoricalRoot(
        fp("root"),
        2,
    )
    assert item.to_dict()["sequence"] == 2
    with pytest.raises(ValueError):
        ProtectedHistoricalRoot(
            "bad",
            1,
        )
    with pytest.raises(ValueError):
        ProtectedHistoricalRoot(
            fp("root"),
            -1,
        )


def test_retention_receipt_chain_capacity_discovery():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=10,
    )
    for index in range(6):
        receipts.append(
            receipt(index)
        )
    _, store = checkpoint_store(backend)
    planner = DurableRetentionPlanner(
        store,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    plan = planner.plan(
        "receipts",
        receipts,
    )
    assert plan.capacity == 10
    assert plan.utilization == 0.6
    assert plan.state is (
        DurableRetentionState.CHECKPOINT_REQUIRED
    )


def test_retention_receipt_chain_archive_recommendation():
    backend = InMemoryFencedStore()
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=10,
    )
    for index in range(4):
        receipts.append(receipt(index))
    _, store = checkpoint_store(backend)
    store.publish("receipts", receipts)
    for index in range(4, 6):
        receipts.append(receipt(index))
    planner = DurableRetentionPlanner(
        store,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    plan = planner.plan(
        "receipts",
        receipts,
    )
    assert plan.archive_through_sequence == 4
    assert plan.estimated_live_after_archive == 2
    assert plan.state is (
        DurableRetentionState.ARCHIVE_RECOMMENDED
    )


def test_checkpoint_and_retention_serialization_are_json_shaped():
    backend, target = journal(
        max_events=10
    )
    append_events(target, 4)
    _, store = checkpoint_store(backend)
    checkpoint = store.publish(
        "journal",
        target,
    )
    append_events(target, 2)
    planner = DurableRetentionPlanner(
        store,
        DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.5,
            warning_utilization=0.7,
            critical_utilization=0.9,
        ),
    )
    plan = planner.plan(
        "journal",
        target,
    )
    checkpoint_data = checkpoint.to_dict()
    plan_data = plan.to_dict()
    assert checkpoint_data[
        "checkpoint_digest"
    ] == checkpoint.checkpoint.digest
    assert plan_data[
        "checkpoint_digest"
    ] == checkpoint.checkpoint.digest
    assert plan_data[
        "archive_through_root"
    ] == checkpoint.checkpoint.root_hash
