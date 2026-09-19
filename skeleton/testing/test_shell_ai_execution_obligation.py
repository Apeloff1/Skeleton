"""Durable execution obligation catalog and recovery tests."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    AIExecutionAttemptStore,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_obligation import (
    AIExecutionObligation,
    AIExecutionObligationStore,
    ExecutionObligationCatalogEntry,
    ExecutionObligationCatalogHead,
    ExecutionObligationCatalogIndex,
    ExecutionObligationConflict,
    ExecutionObligationCorruption,
    ExecutionObligationState,
    GENESIS_HASH,
)
from skeleton.shells.ai.execution_obligation_recovery import (
    AIExecutionObligationRecoveryInspector,
    ExecutionObligationRecoveryDisposition,
    ExecutionObligationRecoveryError,
    ExecutionObligationRecoverySummary,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    AIExecutionFinalizationStore,
    FinalizationPhase,
)


def fp(char: str) -> str:
    return char * 64


def attempt(
    *,
    attempt_id="obligation",
    session_id="session",
    principal="alice",
    worker_id="worker",
    plan_fingerprint=None,
    seal_id=None,
    state=ExecutionAttemptState.AUTHORIZED,
    runtime_trust_digest="",
    release_evidence_digest="",
    terminal_evidence_digest="",
    error_type="",
) -> AIExecutionAttempt:
    plan_fingerprint = plan_fingerprint or fp("p")
    seal_id = seal_id or attempt_id
    if state is ExecutionAttemptState.SUCCEEDED and not terminal_evidence_digest:
        terminal_evidence_digest = fp("v")
    if state is ExecutionAttemptState.FAILED and not error_type:
        error_type = "ExecutionFailed"
    return AIExecutionAttempt(
        1,
        attempt_id,
        session_id,
        principal,
        worker_id,
        plan_fingerprint,
        seal_id,
        state,
        1.0,
        2.0,
        runtime_trust_digest=runtime_trust_digest,
        release_evidence_digest=release_evidence_digest,
        terminal_evidence_digest=terminal_evidence_digest,
        error_type=error_type,
    )


def finalization(
    *,
    finalization_id=None,
    session_id="session",
    attempt_id="obligation",
    attempt_authority_digest=None,
    provenance_digest=None,
) -> AIExecutionFinalization:
    provenance_digest = provenance_digest or fp("v")
    attempt_authority_digest = attempt_authority_digest or fp("a")
    finalization_id = finalization_id or AIExecutionFinalization.derive_id(
        session_id=session_id,
        provenance_digest=provenance_digest,
        execution_attempt_id=attempt_id,
    )
    return AIExecutionFinalization(
        schema_version=1,
        finalization_id=finalization_id,
        session_id=session_id,
        provenance_digest=provenance_digest,
        phase=FinalizationPhase.COMPLETE,
        created_at=1.0,
        updated_at=2.0,
        execution_attempt_id=attempt_id,
        execution_attempt_authority_digest=attempt_authority_digest,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        audit_root=fp("r"),
    )


def register(
    store: AIExecutionObligationStore,
    *,
    obligation_id="obligation",
    session_id="session",
    principal="alice",
    plan_fingerprint=None,
    seal_id=None,
    runtime_trust_digest="",
    release_evidence_digest="",
):
    return store.register(
        obligation_id=obligation_id,
        session_id=session_id,
        principal=principal,
        plan_fingerprint=plan_fingerprint or fp("p"),
        execution_seal_id=seal_id or obligation_id,
        runtime_trust_digest=runtime_trust_digest,
        release_evidence_digest=release_evidence_digest,
    )


class StubRecovery(DurableSessionRecoveryVerifier):
    def __init__(self, status=DurableRecoveryStatus.VERIFIED):
        self.status = status

    def verify(self, finalization_id):
        return SimpleNamespace(
            status=self.status,
            finalization_id=finalization_id,
            to_dict=lambda: {
                "status": self.status.value,
                "finalization_id": finalization_id,
            },
        )


def inspector(
    obligations,
    attempts,
    finalizations,
    *,
    recovery_status=DurableRecoveryStatus.VERIFIED,
    max_scan=100000,
):
    return AIExecutionObligationRecoveryInspector(
        obligations,
        attempts,
        finalizations,
        StubRecovery(recovery_status),
        max_scan=max_scan,
    )


def test_empty_catalog_uses_genesis_root():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    assert store.snapshot() == ()
    assert store.obligations() == ()
    assert store.length() == 0
    assert store.root_hash() == GENESIS_HASH
    assert store.verify()
    assert store.head() == ExecutionObligationCatalogHead(0, GENESIS_HASH)


def test_register_commits_catalog_and_registered_state():
    store = AIExecutionObligationStore(
        InMemoryFencedStore(),
        clock=lambda: 10.0,
    )
    stored = register(store)
    assert stored.revision == 1
    assert stored.obligation.state is ExecutionObligationState.REGISTERED
    assert stored.obligation.created_at == 10.0
    assert stored.obligation.updated_at == 10.0
    assert store.length() == 1
    entry = store.snapshot()[0]
    assert entry.obligation_id == "obligation"
    assert entry.sequence == 1
    assert entry.previous_hash == GENESIS_HASH
    assert entry.authority_digest == stored.obligation.authority_digest
    assert store.verify()


def test_register_is_idempotent_for_same_authority():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    first = register(store)
    second = register(store)
    assert second == first
    assert store.length() == 1
    assert len(store.obligations()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": "other"},
        {"principal": "bob"},
        {"plan_fingerprint": fp("x")},
        {"seal_id": "other-seal"},
        {"runtime_trust_digest": fp("t")},
        {"release_evidence_digest": fp("r")},
    ],
)
def test_register_rejects_authority_substitution(changes):
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    with pytest.raises(
        ExecutionObligationConflict,
        match="differs",
    ):
        register(store, **changes)


def test_multiple_registrations_form_contiguous_catalog():
    store = AIExecutionObligationStore(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    register(store, obligation_id="a", session_id="sa")
    register(store, obligation_id="b", session_id="sb")
    register(store, obligation_id="c", session_id="sc")
    items = store.snapshot()
    assert [item.sequence for item in items] == [1, 2, 3]
    assert items[0].previous_hash == GENESIS_HASH
    assert items[1].previous_hash == items[0].node_hash
    assert items[2].previous_hash == items[1].node_hash
    assert store.root_hash() == items[-1].node_hash
    assert store.verify()


def test_fresh_reader_recovers_catalog_and_states():
    backend = InMemoryFencedStore()
    writer = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    register(writer, obligation_id="a", session_id="sa")
    register(writer, obligation_id="b", session_id="sb")

    reader = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    assert reader.snapshot() == writer.snapshot()
    assert reader.root_hash() == writer.root_hash()
    assert reader.verify()
    assert [
        item.obligation.obligation_id
        for item in reader.obligations()
    ] == ["a", "b"]


def test_missing_state_self_heals_from_committed_catalog():
    backend = InMemoryFencedStore()
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    original = register(store)
    state_key = store._state_key("obligation")
    record = backend.get(store.namespace, state_key)
    backend.delete(
        store.namespace,
        state_key,
        expected_revision=record.revision,
    )

    fresh = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    healed = fresh.current("obligation")
    assert healed is not None
    assert healed.obligation.state is ExecutionObligationState.REGISTERED
    assert healed.obligation.authority_digest == original.obligation.authority_digest


def test_missing_index_self_heals_from_committed_catalog():
    backend = InMemoryFencedStore()
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    register(store)
    index_key = store._index_key("obligation")
    record = backend.get(store.namespace, index_key)
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=record.revision,
    )

    fresh = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    assert fresh.current("obligation") is not None
    assert backend.get(fresh.namespace, index_key) is not None


def test_missing_index_repair_detects_duplicate_committed_obligation_id():
    backend = InMemoryFencedStore()
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
        clock=lambda: 1.0,
    )
    first = register(store).obligation
    first_entry = store.snapshot()[0]
    index_key = store._index_key("obligation")
    index_record = backend.get(store.namespace, index_key)
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )

    second_hash = store._node_hash(
        first_entry.node_hash,
        2,
        obligation_id="obligation",
        session_id="session",
        principal="alice",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
        runtime_trust_digest="",
        release_evidence_digest="",
        created_at=2.0,
    )
    second_entry = ExecutionObligationCatalogEntry(
        2,
        first_entry.node_hash,
        second_hash,
        "obligation",
        "session",
        "alice",
        fp("p"),
        "obligation",
        "",
        "",
        2.0,
    )
    backend.put_if_absent(
        store.namespace,
        store._node_key(second_hash),
        second_entry,
    )
    head_record = backend.get(store.namespace, "head")
    backend.compare_and_swap(
        store.namespace,
        "head",
        expected_revision=head_record.revision,
        value=ExecutionObligationCatalogHead(2, second_hash),
    )
    with pytest.raises(
        ExecutionObligationCorruption,
        match="multiple times",
    ):
        store.current(first.obligation_id)


def test_catalog_node_tamper_breaks_verification():
    backend = InMemoryFencedStore()
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    register(store)
    entry = store.snapshot()[0]
    key = store._node_key(entry.node_hash)
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=replace(entry, principal="mallory"),
    )
    assert not store.verify()
    with pytest.raises(
        ExecutionObligationCorruption,
        match="digest",
    ):
        store.snapshot()


def test_missing_committed_catalog_node_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "obligations",
        "head",
        ExecutionObligationCatalogHead(1, fp("x")),
    )
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    assert not store.verify()
    with pytest.raises(
        ExecutionObligationCorruption,
        match="missing",
    ):
        store.snapshot()


def test_wrong_head_type_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent("obligations", "head", {"bad": True})
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    with pytest.raises(
        ExecutionObligationCorruption,
        match="head type",
    ):
        store.head()
    assert not store.verify()


def test_wrong_state_type_is_corruption():
    backend = InMemoryFencedStore()
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    register(store)
    key = store._state_key("obligation")
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(
        ExecutionObligationCorruption,
        match="state type",
    ):
        store.current("obligation")


def test_state_catalog_authority_mismatch_is_corruption():
    backend = InMemoryFencedStore()
    store = AIExecutionObligationStore(
        backend,
        namespace="obligations",
    )
    register(store)
    key = store._state_key("obligation")
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            principal="mallory",
        ),
    )
    with pytest.raises(
        ExecutionObligationCorruption,
        match="authority mismatch",
    ):
        store.current("obligation")


def test_sync_authorized_attempt_moves_to_attempt_bound():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    value = attempt()
    synced = store.sync_attempt("obligation", value)
    assert synced.obligation.state is ExecutionObligationState.ATTEMPT_BOUND
    assert synced.obligation.attempt_authority_digest == value.authority_digest
    assert synced.obligation.attempt_state == "authorized"
    assert synced.obligation.terminal_evidence_digest == ""


def test_sync_terminal_attempt_updates_existing_bound_state():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    authorized = attempt()
    store.sync_attempt("obligation", authorized)
    succeeded = replace(
        authorized,
        state=ExecutionAttemptState.SUCCEEDED,
        updated_at=2.0,
        terminal_evidence_digest=fp("v"),
    )
    synced = store.sync_attempt("obligation", succeeded)
    assert synced.obligation.attempt_state == "succeeded"
    assert synced.obligation.terminal_evidence_digest == fp("v")


def test_sync_identical_attempt_is_revision_idempotent():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    value = attempt()
    first = store.sync_attempt("obligation", value)
    second = store.sync_attempt("obligation", value)
    assert second == first


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other"),
        ("principal", "bob"),
        ("plan_fingerprint", fp("x")),
        ("execution_seal_id", "other"),
        ("attempt_id", "other"),
    ],
)
def test_sync_attempt_rejects_authority_substitution(field, value):
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    bad = replace(attempt(), **{field: value})
    with pytest.raises(
        ExecutionObligationConflict,
        match="does not match",
    ):
        store.sync_attempt("obligation", bad)


def test_sync_attempt_rejects_runtime_binding_substitution():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store, runtime_trust_digest=fp("t"))
    bad = attempt(runtime_trust_digest=fp("x"))
    with pytest.raises(
        ExecutionObligationConflict,
        match="does not match",
    ):
        store.sync_attempt("obligation", bad)


def test_sync_attempt_rejects_release_binding_substitution():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store, release_evidence_digest=fp("r"))
    bad = attempt(release_evidence_digest=fp("x"))
    with pytest.raises(
        ExecutionObligationConflict,
        match="does not match",
    ):
        store.sync_attempt("obligation", bad)


def test_finalize_requires_attempt_bound_state():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    registered = register(store)
    f = finalization(
        attempt_authority_digest=fp("a"),
    )
    assert registered.obligation.state is ExecutionObligationState.REGISTERED
    with pytest.raises(
        ExecutionObligationConflict,
        match="bind attempt",
    ):
        store.finalize("obligation", f)


def test_finalize_links_complete_finalization():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
        provenance_digest=terminal.terminal_evidence_digest,
    )
    result = store.finalize("obligation", f)
    assert result.obligation.state is ExecutionObligationState.FINALIZED
    assert result.obligation.finalization_id == f.finalization_id
    assert result.obligation.terminal_evidence_digest == fp("v")
    assert len(result.obligation.finalization_digest) == 64
    assert result.obligation.terminal


def test_finalize_identical_retry_is_revision_idempotent():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
        provenance_digest=fp("v"),
    )
    first = store.finalize("obligation", f)
    second = store.finalize("obligation", f)
    assert second == first


def test_finalize_rejects_different_finalization_retry():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
        provenance_digest=fp("v"),
    )
    store.finalize("obligation", f)
    bad = replace(f, audit_anchor_digest=fp("x"))
    with pytest.raises(
        ExecutionObligationConflict,
        match="finalized differently",
    ):
        store.finalize("obligation", bad)


def test_finalize_requires_complete_finalization():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
    )
    incomplete = replace(
        f,
        phase=FinalizationPhase.ANCHORED,
        audit_witness_digest="",
        audit_witness_sequence=None,
        execution_evidence_digest="",
        execution_evidence_chain_node_hash="",
    )
    with pytest.raises(ValueError, match="complete"):
        store.finalize("obligation", incomplete)


def test_finalize_rejects_session_mismatch():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    bad = finalization(
        session_id="other",
        attempt_authority_digest=terminal.authority_digest,
    )
    with pytest.raises(
        ExecutionObligationConflict,
        match="does not match",
    ):
        store.finalize("obligation", bad)


def test_finalize_rejects_attempt_authority_mismatch():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    bad = finalization(
        attempt_authority_digest=fp("x"),
    )
    with pytest.raises(
        ExecutionObligationConflict,
        match="does not match",
    ):
        store.finalize("obligation", bad)


def test_finalize_rejects_terminal_provenance_mismatch():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    bad = finalization(
        attempt_authority_digest=terminal.authority_digest,
        provenance_digest=fp("x"),
    )
    with pytest.raises(
        ExecutionObligationConflict,
        match="provenance",
    ):
        store.finalize("obligation", bad)


def test_retire_registered_obligation_with_proof():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    retired = store.retire(
        "obligation",
        proof_digest=fp("q"),
        reason="verified process boundary was never entered",
    )
    assert retired.obligation.state is ExecutionObligationState.RETIRED
    assert retired.obligation.retirement_proof_digest == fp("q")
    assert retired.obligation.terminal


def test_retire_bound_obligation_with_proof():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    store.sync_attempt("obligation", attempt())
    retired = store.retire(
        "obligation",
        proof_digest=fp("q"),
        reason="authorized attempt was abandoned",
    )
    assert retired.obligation.state is ExecutionObligationState.RETIRED


def test_retire_identical_retry_is_idempotent():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    first = store.retire(
        "obligation",
        proof_digest=fp("q"),
        reason="safe",
    )
    second = store.retire(
        "obligation",
        proof_digest=fp("q"),
        reason="safe",
    )
    assert second == first


def test_retire_different_retry_is_rejected():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    store.retire(
        "obligation",
        proof_digest=fp("q"),
        reason="safe",
    )
    with pytest.raises(
        ExecutionObligationConflict,
        match="retired differently",
    ):
        store.retire(
            "obligation",
            proof_digest=fp("x"),
            reason="different",
        )


def test_finalized_obligation_cannot_be_retired():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    register(store)
    terminal = attempt(
        state=ExecutionAttemptState.SUCCEEDED,
        terminal_evidence_digest=fp("v"),
    )
    store.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
    )
    store.finalize("obligation", f)
    with pytest.raises(
        ExecutionObligationConflict,
        match="finalized",
    ):
        store.retire(
            "obligation",
            proof_digest=fp("q"),
            reason="not allowed",
        )


def test_inspector_registered_without_attempt_is_safe_not_started():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    report = inspector(
        obligations,
        attempts,
        finalizations,
    ).inspect("obligation")
    assert report.disposition is (
        ExecutionObligationRecoveryDisposition.SAFE_NOT_STARTED
    )
    assert report.safe_to_replan
    assert not report.requires_manual_review


def test_inspector_authorized_attempt_is_safe_not_started():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    obligations.sync_attempt("obligation", stored.attempt)
    report = inspector(
        obligations,
        attempts,
        finalizations,
    ).inspect("obligation")
    assert report.disposition is (
        ExecutionObligationRecoveryDisposition.SAFE_NOT_STARTED
    )


def test_inspector_boundary_entered_is_ambiguous_and_never_safe():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    boundary = attempts.enter_boundary(stored.attempt).attempt
    obligations.sync_attempt("obligation", boundary)
    report = inspector(
        obligations,
        attempts,
        finalizations,
    ).inspect("obligation")
    assert report.disposition is (
        ExecutionObligationRecoveryDisposition.AMBIGUOUS_BOUNDARY
    )
    assert report.requires_manual_review
    assert not report.safe_to_replan


@pytest.mark.parametrize(
    "state",
    [ExecutionAttemptState.SUCCEEDED, ExecutionAttemptState.FAILED],
)
def test_terminal_attempt_without_finalization_is_discoverable(state):
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    boundary = attempts.enter_boundary(stored.attempt).attempt
    if state is ExecutionAttemptState.SUCCEEDED:
        terminal = attempts.succeed(
            boundary,
            terminal_evidence_digest=fp("v"),
        ).attempt
    else:
        terminal = attempts.fail(
            boundary,
            error_type="Failed",
            terminal_evidence_digest=fp("v"),
        ).attempt
    obligations.sync_attempt("obligation", terminal)
    report = inspector(
        obligations,
        attempts,
        finalizations,
    ).inspect("obligation")
    assert report.disposition is (
        ExecutionObligationRecoveryDisposition.TERMINAL_UNFINALIZED
    )
    assert report.derived_finalization_id == (
        AIExecutionFinalization.derive_id(
            session_id="session",
            provenance_digest=fp("v"),
            execution_attempt_id="obligation",
        )
    )
    assert report.requires_manual_review


def test_complete_verified_finalization_is_discovered_and_reconciled():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    boundary = attempts.enter_boundary(stored.attempt).attempt
    terminal = attempts.succeed(
        boundary,
        terminal_evidence_digest=fp("v"),
    ).attempt
    obligations.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
        provenance_digest=fp("v"),
    )
    backend.put_if_absent(
        finalizations.namespace,
        finalizations.key(f.finalization_id),
        f,
    )

    recovery = inspector(
        obligations,
        attempts,
        finalizations,
    )
    before = recovery.inspect("obligation")
    assert before.disposition is (
        ExecutionObligationRecoveryDisposition.FINALIZATION_DISCOVERED
    )
    after = recovery.reconcile("obligation")
    assert after.disposition is (
        ExecutionObligationRecoveryDisposition.VERIFIED_FINALIZED
    )
    assert after.verified
    assert obligations.current(
        "obligation"
    ).obligation.state is ExecutionObligationState.FINALIZED


def test_complete_but_unverified_finalization_requires_manual_review():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    boundary = attempts.enter_boundary(stored.attempt).attempt
    terminal = attempts.succeed(
        boundary,
        terminal_evidence_digest=fp("v"),
    ).attempt
    obligations.sync_attempt("obligation", terminal)
    f = finalization(
        attempt_authority_digest=terminal.authority_digest,
    )
    backend.put_if_absent(
        finalizations.namespace,
        finalizations.key(f.finalization_id),
        f,
    )
    report = inspector(
        obligations,
        attempts,
        finalizations,
        recovery_status=DurableRecoveryStatus.MANUAL_REVIEW,
    ).inspect("obligation")
    assert report.disposition is (
        ExecutionObligationRecoveryDisposition.MANUAL_REVIEW
    )


def test_recover_safe_retires_registered_without_attempt():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    recovery = inspector(
        obligations,
        attempts,
        finalizations,
    )
    summary = recovery.recover_safe()
    assert summary.allowed
    assert summary.retired == 1
    assert obligations.current(
        "obligation"
    ).obligation.state is ExecutionObligationState.RETIRED


def test_recover_safe_abandons_authorized_attempt_then_retires():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    obligations.sync_attempt("obligation", stored.attempt)
    summary = inspector(
        obligations,
        attempts,
        finalizations,
    ).recover_safe()
    assert summary.allowed
    assert summary.retired == 1
    assert attempts.current(
        "obligation"
    ).attempt.state is ExecutionAttemptState.ABANDONED


def test_recover_safe_does_not_touch_boundary_ambiguity():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    boundary = attempts.enter_boundary(stored.attempt).attempt
    obligations.sync_attempt("obligation", boundary)
    summary = inspector(
        obligations,
        attempts,
        finalizations,
    ).recover_safe()
    assert not summary.allowed
    assert summary.ambiguous == 1
    assert obligations.current(
        "obligation"
    ).obligation.state is ExecutionObligationState.ATTEMPT_BOUND
    assert attempts.current(
        "obligation"
    ).attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED


def test_require_no_ambiguous_side_effects_rejects_boundary_attempt():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    stored = attempts.reserve(
        attempt_id="obligation",
        session_id="session",
        principal="alice",
        worker_id="worker",
        plan_fingerprint=fp("p"),
        execution_seal_id="obligation",
    )
    boundary = attempts.enter_boundary(stored.attempt).attempt
    obligations.sync_attempt("obligation", boundary)
    with pytest.raises(
        ExecutionObligationRecoveryError,
        match="process boundary",
    ):
        inspector(
            obligations,
            attempts,
            finalizations,
        ).require_no_ambiguous_side_effects()


def test_summary_sorted_and_counts_terminal_states():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations, obligation_id="b", session_id="sb")
    register(obligations, obligation_id="a", session_id="sa")
    recovery = inspector(
        obligations,
        attempts,
        finalizations,
    )
    summary = recovery.recover_safe()
    assert [item.obligation_id for item in summary.reports] == ["a", "b"]
    assert summary.retired == 2
    assert summary.unresolved == 0
    assert summary.allowed


def test_recovery_report_digest_is_stable():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    recovery = inspector(
        obligations,
        attempts,
        finalizations,
    )
    first = recovery.inspect("obligation")
    second = recovery.inspect("obligation")
    assert first.digest == second.digest
    assert first == second


def test_missing_obligation_inspection_is_explicit():
    backend = InMemoryFencedStore()
    recovery = inspector(
        AIExecutionObligationStore(backend),
        AIExecutionAttemptStore(backend),
        AIExecutionFinalizationStore(backend),
    )
    with pytest.raises(
        ExecutionObligationRecoveryError,
        match="missing",
    ):
        recovery.inspect("missing")


@pytest.mark.parametrize("max_scan", [0, -1, True, 1.5])
def test_recovery_scan_bound_validation(max_scan):
    backend = InMemoryFencedStore()
    with pytest.raises(ValueError, match="max_scan"):
        inspector(
            AIExecutionObligationStore(backend),
            AIExecutionAttemptStore(backend),
            AIExecutionFinalizationStore(backend),
            max_scan=max_scan,
        )


def test_recovery_scan_bound_is_enforced():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations, obligation_id="a", session_id="a")
    register(obligations, obligation_id="b", session_id="b")
    recovery = inspector(
        obligations,
        attempts,
        finalizations,
        max_scan=1,
    )
    with pytest.raises(
        ExecutionObligationRecoveryError,
        match="scan bound",
    ):
        recovery.inspect_all()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"namespace": ""},
        {"max_obligations": 0},
        {"max_obligations": True},
        {"max_retries": 0},
        {"max_retries": 129},
        {"max_retries": True},
    ],
)
def test_store_constructor_validation(kwargs):
    with pytest.raises((ValueError, TypeError)):
        AIExecutionObligationStore(
            InMemoryFencedStore(),
            **kwargs,
        )


def test_capacity_exhaustion():
    store = AIExecutionObligationStore(
        InMemoryFencedStore(),
        max_obligations=1,
    )
    register(store, obligation_id="a", session_id="a")
    with pytest.raises(RuntimeError, match="capacity"):
        register(store, obligation_id="b", session_id="b")


def test_obligation_state_validation():
    with pytest.raises(ValueError):
        AIExecutionObligation(
            1,
            "id",
            "session",
            "alice",
            fp("p"),
            "seal",
            ExecutionObligationState.REGISTERED,
            1.0,
            1.0,
            attempt_authority_digest=fp("a"),
        )


def test_catalog_head_validation():
    with pytest.raises(ValueError):
        ExecutionObligationCatalogHead(-1, GENESIS_HASH)
    with pytest.raises(ValueError):
        ExecutionObligationCatalogHead(0, fp("x"))
    with pytest.raises(ValueError):
        ExecutionObligationCatalogHead(1, GENESIS_HASH)


def test_catalog_index_validation():
    with pytest.raises(ValueError):
        ExecutionObligationCatalogIndex(
            "",
            1,
            fp("n"),
            fp("a"),
        )
    with pytest.raises(ValueError):
        ExecutionObligationCatalogIndex(
            "id",
            0,
            fp("n"),
            fp("a"),
        )


def test_obligation_to_dict_contains_authority_and_terminal_flag():
    store = AIExecutionObligationStore(InMemoryFencedStore())
    value = register(store).obligation
    data = value.to_dict()
    assert data["obligation_id"] == "obligation"
    assert data["state"] == "registered"
    assert data["terminal"] is False
    assert len(data["authority_digest"]) == 64


def test_recovery_summary_to_dict():
    backend = InMemoryFencedStore()
    obligations = AIExecutionObligationStore(backend)
    attempts = AIExecutionAttemptStore(backend)
    finalizations = AIExecutionFinalizationStore(backend)
    register(obligations)
    summary = inspector(
        obligations,
        attempts,
        finalizations,
    ).recover_safe()
    data = summary.to_dict()
    assert data["allowed"] is True
    assert data["retired"] == 1
    assert data["unresolved"] == 0
    assert len(data["digest"]) == 64
