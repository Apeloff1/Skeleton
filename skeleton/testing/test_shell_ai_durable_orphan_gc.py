"""Maintenance-gated durable orphan garbage collection tests."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_destruction import DurableDestructionLedger
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceGuard,
    DurableMaintenanceOperation,
    DurableMaintenanceStale,
    DurableMaintenanceStore,
)
from skeleton.shells.ai.durable_orphan_gc import (
    DurableOrphanDeleteState,
    DurableOrphanGCManualReview,
    DurableOrphanGCOperator,
    DurableOrphanGCPlan,
    DurableOrphanGCPolicy,
    DurableOrphanGCResult,
    DurableOrphanGCStale,
)
from skeleton.shells.ai.durable_orphan_scan import (
    DurableOrphanScanPolicy,
    DurableOrphanScanner,
)
from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


GENESIS = "0" * 64


def fp(char: str) -> str:
    return char * 64


class Clock:
    def __init__(self, value: float = 100.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def receipt(
    name: str,
    *,
    fingerprint: str | None = None,
    receipt_id: str | None = None,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{name}",
        fingerprint=fingerprint or fp("a"),
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
        receipt_id=receipt_id or f"receipt-{name}",
    )


def orphan_event(
    journal: DistributedAIDecisionJournal,
    *,
    name="orphan",
    sequence=1,
    previous_hash=GENESIS,
    observed_at=101.0,
) -> AIDecisionEvent:
    payload = MappingProxyType({"name": name})
    digest = AIDecisionJournal._hash(
        previous_hash,
        sequence,
        name,
        observed_at,
        f"session-{name}",
        f"intent-{name}",
        f"proposal-{name}",
        name,
        payload,
    )
    event = AIDecisionEvent(
        sequence,
        previous_hash,
        digest,
        name,
        observed_at,
        f"session-{name}",
        f"intent-{name}",
        f"proposal-{name}",
        name,
        payload,
    )
    journal.backend.put_if_absent(
        journal.namespace,
        journal._event_key(digest),
        event,
    )
    return event


def orphan_receipt(
    chain: DistributedReceiptChain,
    *,
    name="orphan",
    sequence=1,
    previous_hash=GENESIS,
) -> ChainedReceipt:
    value = receipt(
        name,
        fingerprint=fp("b"),
    )
    digest = ReceiptChain._hash(
        previous_hash,
        sequence,
        value,
    )
    item = ChainedReceipt(
        sequence,
        previous_hash,
        digest,
        value,
    )
    chain.backend.put_if_absent(
        chain.namespace,
        chain._node_key(digest),
        item,
    )
    return item


def environment(
    *,
    kind="journal",
    clock=None,
    gc_policy=None,
    scan_policy=None,
):
    clock = clock or Clock()
    backend = InMemoryFencedStore(
        clock=clock,
    )
    if kind == "journal":
        chain = DistributedAIDecisionJournal(
            backend,
            namespace="chain",
            clock=clock,
        )
        committed = chain.append(
            "committed",
            session_id="session",
            intent_id="intent",
            proposal_id="proposal",
        )
        orphan = orphan_event(
            chain,
            observed_at=clock.value + 1.0,
        )
    else:
        chain = DistributedReceiptChain(
            backend,
            namespace="chain",
        )
        committed = chain.append(
            receipt("committed")
        )
        orphan = orphan_receipt(chain)

    scanner = DurableOrphanScanner(
        policy=(
            scan_policy
            or DurableOrphanScanPolicy()
        ),
        clock=clock,
    )
    destruction_ledger = DurableDestructionLedger(
        backend,
        ArtifactSigner(
            "orphan-gc-destruction",
            b"d" * 32,
            clock=clock,
        ),
        namespace="destruction",
        clock=clock,
    )
    operator = DurableOrphanGCOperator(
        scanner,
        policy=(
            gc_policy
            or DurableOrphanGCPolicy()
        ),
        destruction_ledger=destruction_ledger,
        clock=clock,
    )
    signer = ArtifactSigner(
        "orphan-gc-maintenance",
        b"k" * 32,
        clock=clock,
    )
    maintenance_store = DurableMaintenanceStore(
        backend,
        signer,
        namespace="maintenance",
        clock=clock,
        nonce_factory=lambda: "nonce",
    )
    return (
        clock,
        backend,
        chain,
        committed,
        orphan,
        scanner,
        operator,
        maintenance_store,
    )


def guard_for(
    operator,
    store,
    chain,
    *,
    chain_id="chain-id",
    operation=DurableMaintenanceOperation.ORPHAN_GC,
):
    resource = operator.maintenance_resource(
        chain_id,
        chain,
    )
    signed = store.acquire(
        operation,
        owner_id="operator",
        resources=(resource,),
        ttl_seconds=60.0,
    )
    return DurableMaintenanceGuard(
        store,
        signed,
    )


def test_plan_selects_exact_journal_orphan():
    (
        _,
        _,
        chain,
        committed,
        orphan,
        _,
        operator,
        _,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    assert len(plan.targets) == 1
    target = plan.targets[0]
    assert target.node_hash == orphan.event_hash
    assert target.node_hash != committed.event_hash
    assert target.sequence == 1
    assert not plan.empty
    assert plan.chain_id == "chain-id"
    assert len(plan.plan_id) == 64
    assert len(plan.digest) == 64


def test_plan_selects_exact_receipt_orphan():
    (
        _,
        _,
        chain,
        committed,
        orphan,
        _,
        operator,
        _,
    ) = environment(kind="receipt")
    plan = operator.plan(
        "chain-id",
        chain,
    )
    assert len(plan.targets) == 1
    assert (
        plan.targets[0].node_hash
        == orphan.receipt_hash
    )
    assert (
        plan.targets[0].node_hash
        != committed.receipt_hash
    )


def test_execute_deletes_journal_orphan_and_preserves_chain():
    (
        _,
        backend,
        chain,
        committed,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    assert result.ok
    assert result.deleted == 1
    assert result.already_absent == 0
    assert result.blocked == 0
    assert (
        backend.get(
            chain.namespace,
            chain._event_key(
                orphan.event_hash
            ),
        )
        is None
    )
    assert (
        chain.root_hash()
        == committed.event_hash
    )
    assert chain.verify()
    assert operator.verify_result(
        plan,
        result,
        chain,
    )


def test_execute_deletes_receipt_orphan_and_preserves_chain():
    (
        _,
        backend,
        chain,
        committed,
        orphan,
        _,
        operator,
        store,
    ) = environment(kind="receipt")
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    assert result.ok
    assert result.deleted == 1
    assert (
        backend.get(
            chain.namespace,
            chain._node_key(
                orphan.receipt_hash
            ),
        )
        is None
    )
    assert (
        chain.root_hash()
        == committed.receipt_hash
    )
    assert chain.verify()


def test_execute_is_idempotent_when_target_already_absent():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    target = plan.targets[0]
    backend.delete(
        target.backend_namespace,
        target.backend_key,
        expected_revision=(
            target.expected_revision
        ),
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    assert result.ok
    assert result.deleted == 0
    assert result.already_absent == 1
    assert result.results[0].state is (
        DurableOrphanDeleteState.ALREADY_ABSENT
    )
    assert orphan.event_hash != chain.root_hash()


def test_wrong_maintenance_operation_blocks_delete():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
        operation=(
            DurableMaintenanceOperation.COMPACTION
        ),
    )
    with pytest.raises(
        DurableMaintenanceStale,
        match="operation",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )
    assert (
        backend.get(
            chain.namespace,
            chain._event_key(
                orphan.event_hash
            ),
        )
        is not None
    )


def test_head_change_after_authority_acquisition_blocks_delete():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    chain.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    with pytest.raises(
        DurableMaintenanceStale,
        match="state changed",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )
    assert (
        backend.get(
            chain.namespace,
            chain._event_key(
                orphan.event_hash
            ),
        )
        is not None
    )


def test_candidate_becoming_sequence_authority_blocks_delete():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    key = chain._sequence_key(1)
    record = backend.get(
        chain.namespace,
        key,
    )
    backend.compare_and_swap(
        chain.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            orphan.event_hash,
        ),
    )
    with pytest.raises(
        DurableOrphanGCManualReview,
        match="sequence-index",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )
    assert (
        backend.get(
            chain.namespace,
            chain._event_key(
                orphan.event_hash
            ),
        )
        is not None
    )


def test_receipt_candidate_becoming_sequence_authority_blocks_delete():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment(kind="receipt")
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    key = chain._sequence_key(1)
    record = backend.get(
        chain.namespace,
        key,
    )
    backend.compare_and_swap(
        chain.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            orphan.receipt_hash,
        ),
    )
    with pytest.raises(
        DurableOrphanGCManualReview,
        match="sequence-index",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )


def test_candidate_revision_change_blocks_delete_as_stale():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    target = plan.targets[0]
    record = backend.get(
        target.backend_namespace,
        target.backend_key,
    )
    backend.compare_and_swap(
        target.backend_namespace,
        target.backend_key,
        expected_revision=record.revision,
        value=record.value,
    )
    with pytest.raises(
        DurableOrphanGCStale,
        match="revision",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )
    assert (
        backend.get(
            chain.namespace,
            chain._event_key(
                orphan.event_hash
            ),
        )
        is not None
    )


def test_candidate_content_change_blocks_delete_manual_review():
    (
        _,
        backend,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    target = plan.targets[0]
    record = backend.get(
        target.backend_namespace,
        target.backend_key,
    )
    backend.compare_and_swap(
        target.backend_namespace,
        target.backend_key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            summary="tampered",
        ),
    )
    with pytest.raises(
        DurableOrphanGCStale,
        match="revision",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )


def test_plan_age_bound_blocks_old_plan():
    clock = Clock()
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment(
        clock=clock,
        gc_policy=DurableOrphanGCPolicy(
            max_scan_age_seconds=10.0,
        ),
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    clock.advance(11.0)
    with pytest.raises(
        DurableOrphanGCStale,
        match="maximum age",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )


def test_future_plan_clock_blocks_execution():
    clock = Clock()
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment(
        clock=clock,
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    clock.value = plan.created_at - 1.0
    with pytest.raises(
        DurableOrphanGCStale,
        match="future",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )


def test_gc_policy_change_invalidates_plan():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    operator.policy = DurableOrphanGCPolicy(
        max_delete_targets=32,
    )
    with pytest.raises(
        DurableOrphanGCStale,
        match="policy changed",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )


def test_scanner_policy_change_invalidates_plan():
    (
        _,
        _,
        chain,
        _,
        _,
        scanner,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    scanner.policy = DurableOrphanScanPolicy(
        include_reachable=True,
    )
    with pytest.raises(
        DurableOrphanGCStale,
        match="scanner policy",
    ):
        operator.execute(
            plan,
            chain,
            maintenance=guard,
        )


def test_plan_respects_target_limit():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    for index in range(4):
        orphan_event(
            chain,
            name=f"extra-{index}",
            observed_at=120.0 + index,
        )
    plan = operator.plan(
        "chain-id",
        chain,
        max_targets=2,
    )
    assert len(plan.targets) == 2


@pytest.mark.parametrize(
    "limit",
    [0, -1, True, 257],
)
def test_plan_target_limit_validation(limit):
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    with pytest.raises(
        ValueError,
        match="max_targets",
    ):
        operator.plan(
            "chain-id",
            chain,
            max_targets=limit,
        )


def test_manual_review_scan_blocks_plan():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        _,
    ) = environment()
    key = chain._sequence_key(1)
    record = backend.get(
        chain.namespace,
        key,
    )
    backend.compare_and_swap(
        chain.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            orphan.event_hash,
        ),
    )
    with pytest.raises(
        DurableOrphanGCManualReview,
        match="authority conflicts",
    ):
        operator.plan(
            "chain-id",
            chain,
        )


def test_empty_plan_is_serializable_and_non_destructive():
    clock = Clock()
    backend = InMemoryFencedStore(
        clock=clock,
    )
    chain = DistributedAIDecisionJournal(
        backend,
        namespace="chain",
        clock=clock,
    )
    chain.append(
        "committed",
        session_id="session",
        intent_id="intent",
    )
    scanner = DurableOrphanScanner(
        clock=clock,
    )
    operator = DurableOrphanGCOperator(
        scanner,
        clock=clock,
    )
    store = DurableMaintenanceStore(
        backend,
        ArtifactSigner(
            "maintenance",
            b"k" * 32,
            clock=clock,
        ),
        namespace="maintenance",
        clock=clock,
        nonce_factory=lambda: "nonce",
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    assert plan.empty
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    assert result.ok
    assert result.results == ()
    assert result.deleted == 0


def test_plan_id_rejects_mutated_target_binding():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    target = replace(
        plan.targets[0],
        sequence=2,
    )
    with pytest.raises(
        ValueError,
        match="plan_id",
    ):
        DurableOrphanGCPlan(
            plan.schema_version,
            plan.plan_id,
            plan.chain_id,
            plan.node_kind,
            plan.policy_digest,
            plan.scanner_policy_digest,
            plan.scan_digest,
            plan.head_sequence,
            plan.head_root,
            plan.floor_sequence,
            plan.floor_root,
            plan.floor_active,
            (target,),
            plan.created_at,
        )


def test_plan_id_rejects_mutated_head_binding():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    with pytest.raises(
        ValueError,
        match="plan_id",
    ):
        replace(
            plan,
            head_root=fp("x"),
        )


def test_plan_digest_is_stable():
    clock = Clock()
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment(
        clock=clock,
    )
    first = operator.plan(
        "chain-id",
        chain,
    )
    second = operator.plan(
        "chain-id",
        chain,
    )
    assert first.plan_id == second.plan_id
    assert first.digest == second.digest
    assert first == second


def test_plan_digest_changes_with_candidate_set():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    first = operator.plan(
        "chain-id",
        chain,
    )
    orphan_event(
        chain,
        name="second-orphan",
        observed_at=150.0,
    )
    second = operator.plan(
        "chain-id",
        chain,
    )
    assert first.plan_id != second.plan_id
    assert first.digest != second.digest


def test_result_serialization_and_digest():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    data = result.to_dict()
    assert data["ok"] is True
    assert data["deleted"] == 1
    assert data["blocked"] == 0
    assert data["digest"] == result.digest
    assert len(result.digest) == 64


def test_verify_result_rejects_wrong_plan():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    altered = replace(
        result,
        plan_digest=fp("x"),
    )
    assert not operator.verify_result(
        plan,
        altered,
        chain,
    )


def test_verify_result_rejects_reappearing_target():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    backend.put_if_absent(
        chain.namespace,
        chain._event_key(
            orphan.event_hash
        ),
        orphan,
    )
    assert not operator.verify_result(
        plan,
        result,
        chain,
    )


def test_maintenance_resource_binds_floor_and_head_state():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    resource = operator.maintenance_resource(
        "chain-id",
        chain,
    )
    assert resource.resource_id == "chain-id"
    assert resource.resource_kind == "orphan-gc-chain"
    assert resource.sequence == chain.head().sequence
    assert resource.root_hash == chain.head().root_hash
    assert len(resource.state_digest) == 64


def test_maintenance_resource_changes_when_head_changes():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    first = operator.maintenance_resource(
        "chain-id",
        chain,
    )
    chain.append(
        "next",
        session_id="next",
        intent_id="next",
    )
    second = operator.maintenance_resource(
        "chain-id",
        chain,
    )
    assert first != second
    assert first.state_digest != second.state_digest


@pytest.mark.parametrize(
    "value",
    [0, -1, True, 1.2],
)
def test_gc_policy_target_bound_validation(value):
    with pytest.raises(ValueError):
        DurableOrphanGCPolicy(
            max_delete_targets=value
        )


@pytest.mark.parametrize(
    "value",
    [0.0, -1.0, float("nan"), True],
)
def test_gc_policy_age_validation(value):
    with pytest.raises(ValueError):
        DurableOrphanGCPolicy(
            max_scan_age_seconds=value
        )


@pytest.mark.parametrize(
    "name,value",
    [
        (
            "require_chain_verification_after_each_delete",
            1,
        ),
        (
            "require_empty_manual_review",
            "yes",
        ),
    ],
)
def test_gc_policy_boolean_validation(name, value):
    with pytest.raises(ValueError, match="bool"):
        DurableOrphanGCPolicy(
            **{name: value}
        )


def test_gc_policy_digest_is_stable():
    assert (
        DurableOrphanGCPolicy().digest
        == DurableOrphanGCPolicy().digest
    )


def test_operator_constructor_type_validation():
    with pytest.raises(TypeError, match="scanner"):
        DurableOrphanGCOperator(
            object()
        )
    with pytest.raises(TypeError, match="policy"):
        DurableOrphanGCOperator(
            DurableOrphanScanner(),
            policy=object(),
        )
    with pytest.raises(TypeError, match="clock"):
        DurableOrphanGCOperator(
            DurableOrphanScanner(),
            clock=object(),
        )


def test_execute_type_validation():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    with pytest.raises(TypeError, match="plan"):
        operator.execute(
            object(),
            chain,
            maintenance=guard,
        )
    with pytest.raises(TypeError, match="maintenance"):
        operator.execute(
            plan,
            chain,
            maintenance=object(),
        )


def test_scan_conflict_never_deletes_even_if_manual_review_policy_disabled():
    (
        _,
        backend,
        chain,
        _,
        orphan,
        scanner,
        _,
        store,
    ) = environment()
    operator = DurableOrphanGCOperator(
        scanner,
        policy=DurableOrphanGCPolicy(
            require_empty_manual_review=False,
        ),
        clock=lambda: 100.0,
    )
    key = chain._sequence_key(1)
    record = backend.get(
        chain.namespace,
        key,
    )
    backend.compare_and_swap(
        chain.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            orphan.event_hash,
        ),
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    assert plan.empty
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    assert result.deleted == 0
    assert (
        backend.get(
            chain.namespace,
            chain._event_key(
                orphan.event_hash
            ),
        )
        is not None
    )


def test_multiple_orphans_are_deleted_in_plan_order():
    (
        _,
        backend,
        chain,
        _,
        first_orphan,
        _,
        operator,
        store,
    ) = environment()
    second = orphan_event(
        chain,
        name="second",
        observed_at=130.0,
    )
    third = orphan_event(
        chain,
        name="third",
        observed_at=131.0,
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    assert len(plan.targets) == 3
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    assert result.deleted == 3
    for item in (
        first_orphan,
        second,
        third,
    ):
        assert (
            backend.get(
                chain.namespace,
                chain._event_key(
                    item.event_hash
                ),
            )
            is None
        )
    assert chain.verify()


def test_delete_target_digests_are_unique_for_multiple_orphans():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    orphan_event(
        chain,
        name="second",
        observed_at=130.0,
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    digests = tuple(
        item.digest
        for item in plan.targets
    )
    assert len(digests) == len(set(digests))


def test_plan_rejects_manual_review_with_corrupt_node():
    (
        _,
        backend,
        chain,
        _,
        _,
        _,
        operator,
        _,
    ) = environment()
    backend.put_if_absent(
        chain.namespace,
        "event:" + fp("z"),
        {"bad": True},
    )
    with pytest.raises(
        DurableOrphanGCManualReview,
    ):
        operator.plan(
            "chain-id",
            chain,
        )

def test_orphan_gc_emits_signed_destruction_record():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    assert result.destruction_record_id
    assert result.destruction_record_digest
    destruction = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    assert destruction is not None
    assert destruction.record_id == result.destruction_record_id
    assert destruction.record.digest == result.destruction_record_digest
    assert destruction.record.authority_id == guard.signed.epoch_id
    assert destruction.record.authority_digest == guard.signed.epoch.digest
    assert destruction.record.manifest_digest == plan.digest
    assert destruction.record.post_verified
    assert operator.destruction_ledger.require_verified(
        "chain-id"
    ).ok


def test_orphan_gc_destruction_record_binds_plan_chain_state():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    record = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    ).record
    assert record.before_sequence == plan.head_sequence
    assert record.before_root == plan.head_root
    assert record.before_floor_sequence == plan.floor_sequence
    assert record.before_floor_root == plan.floor_root
    assert record.after_sequence == chain.head().sequence
    assert record.after_root == chain.head().root_hash
    assert record.after_floor_sequence == plan.floor_sequence
    assert record.after_floor_root == plan.floor_root
    assert record.deleted_count == result.deleted
    assert record.already_absent_count == result.already_absent


def test_orphan_gc_destruction_item_binds_target():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    record = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    ).record
    assert len(record.items) == len(plan.targets)
    target = plan.targets[0]
    item = record.items[0]
    assert item.backend_namespace == target.backend_namespace
    assert item.backend_key == target.backend_key
    assert item.node_hash == target.node_hash
    assert item.expected_revision == target.expected_revision
    assert item.sequence == target.sequence
    assert not item.archived
    assert item.state.value == "deleted"
    assert result.deleted == 1


def test_receipt_orphan_gc_emits_destruction_record():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment(kind="receipt")
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    destruction = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    assert destruction is not None
    assert destruction.record.items[0].item_kind == plan.node_kind.value
    assert destruction.record.items[0].node_hash == plan.targets[0].node_hash
    assert result.destruction_record_id == destruction.record_id


def test_already_absent_orphan_is_recorded_as_already_absent():
    (
        _,
        backend,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    target = plan.targets[0]
    backend.delete(
        target.backend_namespace,
        target.backend_key,
        expected_revision=target.expected_revision,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    destruction = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    assert result.already_absent == 1
    assert destruction.record.already_absent_count == 1
    assert destruction.record.deleted_count == 0
    assert destruction.record.items[0].state.value == "already_absent"


def test_empty_orphan_gc_plan_does_not_emit_destruction_record():
    clock = Clock()
    backend = InMemoryFencedStore(
        clock=clock,
    )
    chain = DistributedAIDecisionJournal(
        backend,
        namespace="empty-chain",
        clock=clock,
    )
    chain.append(
        "committed",
        session_id="session",
        intent_id="intent",
    )
    destruction_ledger = DurableDestructionLedger(
        backend,
        ArtifactSigner(
            "empty-destruction",
            b"d" * 32,
            clock=clock,
        ),
        namespace="empty-destruction",
        clock=clock,
    )
    operator = DurableOrphanGCOperator(
        DurableOrphanScanner(clock=clock),
        destruction_ledger=destruction_ledger,
        clock=clock,
    )
    maintenance_store = DurableMaintenanceStore(
        backend,
        ArtifactSigner(
            "empty-maintenance",
            b"m" * 32,
            clock=clock,
        ),
        namespace="empty-maintenance",
        clock=clock,
        nonce_factory=lambda: "nonce",
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    assert plan.empty
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            maintenance_store,
            chain,
        ),
    )
    assert result.ok
    assert result.destruction_record_id == ""
    assert result.destruction_record_digest == ""
    assert destruction_ledger.snapshot(
        "chain-id"
    ) == ()


def test_orphan_gc_result_serializes_destruction_evidence():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    data = result.to_dict()
    assert data["destruction_record_id"] == result.destruction_record_id
    assert (
        data["destruction_record_digest"]
        == result.destruction_record_digest
    )
    assert len(data["destruction_record_id"]) == 64


def test_verify_result_requires_destruction_record_when_ledger_enabled():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    stripped = replace(
        result,
        destruction_record_id="",
        destruction_record_digest="",
    )
    assert not operator.verify_result(
        plan,
        stripped,
        chain,
    )


def test_verify_result_rejects_destruction_record_id_substitution():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    altered = replace(
        result,
        destruction_record_id=fp("x"),
        destruction_record_digest=fp("x"),
    )
    assert not operator.verify_result(
        plan,
        altered,
        chain,
    )


def test_fresh_destruction_reader_verifies_orphan_gc_record():
    (
        _,
        backend,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    fresh = DurableDestructionLedger(
        backend,
        ArtifactSigner(
            "orphan-gc-destruction",
            b"d" * 32,
            clock=lambda: 100.0,
        ),
        namespace="destruction",
        clock=lambda: 100.0,
    )
    found = fresh.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    assert found.record_id == result.destruction_record_id
    assert fresh.require_verified(
        "chain-id"
    ).ok


def test_orphan_gc_destruction_index_repairs_after_loss():
    (
        _,
        backend,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    destruction = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    key = operator.destruction_ledger._operation_index_key(
        destruction.operation_key
    )
    record = backend.get(
        operator.destruction_ledger.namespace,
        key,
    )
    backend.delete(
        operator.destruction_ledger.namespace,
        key,
        expected_revision=record.revision,
    )
    repaired = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    assert repaired.record_id == result.destruction_record_id


def test_verify_result_fails_on_destruction_signature_tamper():
    (
        _,
        backend,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    key = operator.destruction_ledger._record_key(
        result.destruction_record_id
    )
    stored = backend.get(
        operator.destruction_ledger.namespace,
        key,
    )
    raw = dict(stored.value)
    signature = dict(raw["signature"])
    signature["signature"] = "f" * 64
    raw["signature"] = signature
    backend.compare_and_swap(
        operator.destruction_ledger.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    assert not operator.verify_result(
        plan,
        result,
        chain,
    )


def test_orphan_gc_operator_rejects_wrong_destruction_ledger_type():
    with pytest.raises(
        TypeError,
        match="destruction_ledger",
    ):
        DurableOrphanGCOperator(
            DurableOrphanScanner(),
            destruction_ledger=object(),
        )


def test_multiple_orphan_deletions_share_one_destruction_record():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    orphan_event(
        chain,
        name="second-ledger",
        observed_at=130.0,
    )
    orphan_event(
        chain,
        name="third-ledger",
        observed_at=131.0,
    )
    plan = operator.plan(
        "chain-id",
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard_for(
            operator,
            store,
            chain,
        ),
    )
    destruction = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    assert len(plan.targets) == 3
    assert len(destruction.record.items) == 3
    assert destruction.record.deleted_count == 3
    assert result.deleted == 3
    assert len(
        operator.destruction_ledger.snapshot(
            "chain-id"
        )
    ) == 1


def test_orphan_gc_destruction_record_binds_maintenance_fence():
    (
        _,
        _,
        chain,
        _,
        _,
        _,
        operator,
        store,
    ) = environment()
    plan = operator.plan(
        "chain-id",
        chain,
    )
    guard = guard_for(
        operator,
        store,
        chain,
    )
    result = operator.execute(
        plan,
        chain,
        maintenance=guard,
    )
    destruction = operator.destruction_ledger.find_operation(
        "chain-id",
        "orphan_gc",
        plan.plan_id,
    )
    claim = next(
        item
        for item in guard.signed.epoch.claims
        if item.resource_id == "chain-id"
    )
    assert destruction.record.fencing_token == claim.fencing_token
    assert destruction.record.authority_id == result.maintenance_epoch_id
