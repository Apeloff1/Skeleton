"""Crash-safe execution evidence finalization state tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    AIExecutionFinalizationStore,
    ExecutionFinalizationConflict,
    FinalizationPhase,
    FinalizationRecovery,
)


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def reserve(store, **changes):
    values = dict(
        session_id="session",
        provenance_digest=fp("p"),
        execution_attempt_id="seal-1",
        execution_attempt_authority_digest=fp("a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    values.update(changes)
    return store.reserve(**values)


def advance_session(store, item):
    return store.advance(
        item,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("s"),
    ).finalization


def advance_checkpoint(store, item):
    return store.advance(
        item,
        FinalizationPhase.CHECKPOINTED,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
    ).finalization


def advance_anchor(store, item):
    return store.advance(
        item,
        FinalizationPhase.ANCHORED,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        audit_root=fp("r"),
    ).finalization


def advance_witness(store, item):
    return store.advance(
        item,
        FinalizationPhase.WITNESSED,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        audit_root=fp("r"),
        audit_witness_digest=fp("w"),
        audit_witness_sequence=1,
    ).finalization


def advance_signed(store, item):
    return store.advance(
        item,
        FinalizationPhase.SIGNED,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        audit_root=fp("r"),
        audit_witness_digest=fp("w"),
        audit_witness_sequence=1,
        execution_evidence_digest=fp("e"),
        execution_evidence_chain_node_hash=fp("x"),
    ).finalization


def advance_complete(store, item):
    return store.advance(
        item,
        FinalizationPhase.COMPLETE,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        audit_root=fp("r"),
        audit_witness_digest=(
            item.audit_witness_digest
        ),
        audit_witness_sequence=item.audit_witness_sequence,
        execution_evidence_digest=item.execution_evidence_digest,
        execution_evidence_chain_node_hash=(
            item.execution_evidence_chain_node_hash
        ),
    ).finalization


def test_finalization_id_is_deterministic():
    first = AIExecutionFinalization.derive_id(
        session_id="session",
        provenance_digest=fp("p"),
        execution_attempt_id="attempt",
    )
    second = AIExecutionFinalization.derive_id(
        session_id="session",
        provenance_digest=fp("p"),
        execution_attempt_id="attempt",
    )
    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other"),
        ("provenance_digest", fp("q")),
        ("execution_attempt_id", "other-attempt"),
    ],
)
def test_finalization_id_changes_with_identity(field, value):
    values = dict(
        session_id="session",
        provenance_digest=fp("p"),
        execution_attempt_id="attempt",
    )
    first = AIExecutionFinalization.derive_id(**values)
    values[field] = value
    second = AIExecutionFinalization.derive_id(**values)
    assert first != second


def test_reserve_creates_started_record():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    stored = reserve(store)
    assert stored.revision == 1
    assert stored.finalization.phase is FinalizationPhase.STARTED
    assert stored.finalization.recovery is FinalizationRecovery.RESUME
    assert stored.finalization.execution_attempt_id == "seal-1"
    assert stored.finalization.runtime_trust_digest == fp("t")
    assert stored.finalization.release_evidence_digest == fp("r")


def test_reserve_is_idempotent_for_same_binding():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    first = reserve(store)
    second = reserve(store)
    assert first == second
    assert second.revision == 1


def test_reserve_rejects_same_id_with_different_binding():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    first = reserve(store, finalization_id="fixed")
    assert first.finalization.finalization_id == "fixed"
    with pytest.raises(ExecutionFinalizationConflict, match="different"):
        reserve(
            store,
            finalization_id="fixed",
            provenance_digest=fp("x"),
        )


def test_full_finalization_progression():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    item = advance_session(store, item)
    assert item.phase is FinalizationPhase.SESSION_EVIDENCE
    item = advance_checkpoint(store, item)
    assert item.phase is FinalizationPhase.CHECKPOINTED
    item = advance_anchor(store, item)
    assert item.phase is FinalizationPhase.ANCHORED
    item = advance_witness(store, item)
    assert item.phase is FinalizationPhase.WITNESSED
    item = advance_signed(store, item)
    assert item.phase is FinalizationPhase.SIGNED
    item = advance_complete(store, item)
    assert item.phase is FinalizationPhase.COMPLETE
    assert item.recovery is FinalizationRecovery.COMPLETE
    assert store.require_complete(item.finalization_id) == item


def test_complete_can_skip_optional_witness_and_signed_bundle():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    item = advance_session(store, item)
    item = advance_checkpoint(store, item)
    item = advance_anchor(store, item)
    item = store.advance(
        item,
        FinalizationPhase.COMPLETE,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        audit_root=fp("r"),
    ).finalization
    assert item.phase is FinalizationPhase.COMPLETE
    assert item.audit_witness_digest == ""
    assert item.execution_evidence_digest == ""


def test_same_phase_retry_does_not_create_revision():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    started = reserve(store)
    first = store.advance(
        started.finalization,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("s"),
    )
    second = store.advance(
        first.finalization,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("s"),
    )
    assert second.revision == first.revision
    assert second.finalization == first.finalization


def test_same_phase_retry_rejects_different_evidence():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = advance_session(store, reserve(store).finalization)
    with pytest.raises(ExecutionFinalizationConflict, match="different evidence"):
        store.advance(
            item,
            FinalizationPhase.SESSION_EVIDENCE,
            session_evidence_digest=fp("x"),
        )


def test_phase_regression_is_noop():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    item = advance_session(store, item)
    checkpointed = store.advance(
        item,
        FinalizationPhase.CHECKPOINTED,
        session_evidence_digest=fp("s"),
        recovery_checkpoint_digest=fp("c"),
    )
    regressed = store.advance(
        checkpointed.finalization,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("s"),
    )
    assert regressed == checkpointed


def test_binding_digest_ignores_phase_and_progress():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    start = reserve(store).finalization
    later = advance_anchor(
        store,
        advance_checkpoint(
            store,
            advance_session(store, start),
        ),
    )
    assert start.binding_digest == later.binding_digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other"),
        ("provenance_digest", fp("x")),
        ("execution_attempt_id", "other"),
        ("execution_attempt_authority_digest", fp("x")),
        ("runtime_trust_digest", fp("x")),
        ("release_evidence_digest", fp("x")),
    ],
)
def test_binding_digest_changes_for_bound_authority(field, value):
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    changed = replace(item, **{field: value})
    assert changed.binding_digest != item.binding_digest


def test_recovery_mapping_by_phase():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    assert item.recovery is FinalizationRecovery.RESUME
    item = advance_session(store, item)
    assert item.recovery is FinalizationRecovery.RESUME
    item = advance_checkpoint(store, item)
    assert item.recovery is FinalizationRecovery.RESUME
    item = advance_anchor(store, item)
    assert item.recovery is FinalizationRecovery.VERIFY_ANCHOR
    item = advance_witness(store, item)
    assert item.recovery is FinalizationRecovery.VERIFY_WITNESS
    item = advance_signed(store, item)
    assert item.recovery is FinalizationRecovery.VERIFY_SIGNED_EVIDENCE
    item = advance_complete(store, item)
    assert item.recovery is FinalizationRecovery.COMPLETE


def test_note_error_preserves_phase_and_evidence():
    now = [10.0]
    store = AIExecutionFinalizationStore(
        InMemoryFencedStore(clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    item = advance_session(store, reserve(store).finalization)
    now[0] = 11.0
    noted = store.note_error(item, RuntimeError("boom"))
    assert noted.finalization.phase is FinalizationPhase.SESSION_EVIDENCE
    assert noted.finalization.session_evidence_digest == fp("s")
    assert noted.finalization.error_count == 1
    assert noted.finalization.last_error_type == "RuntimeError"
    assert noted.finalization.last_error_at == 11


def test_note_error_accumulates_count():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    first = store.note_error(item, ValueError("one"))
    second = store.note_error(first.finalization, OSError("two"))
    assert second.finalization.error_count == 2
    assert second.finalization.last_error_type == "OSError"


def test_require_complete_rejects_incomplete():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    with pytest.raises(ExecutionFinalizationConflict, match="not complete"):
        store.require_complete(item.finalization_id)


def test_current_missing_returns_none():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    assert store.current("missing") is None


def test_key_is_deterministic_and_hides_raw_id():
    first = AIExecutionFinalizationStore.key("secret-ish-id")
    second = AIExecutionFinalizationStore.key("secret-ish-id")
    assert first == second
    assert "secret-ish-id" not in first
    assert first.startswith("finalization:")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"finalization_id": ""},
        {"session_id": ""},
        {"provenance_digest": "bad"},
        {"runtime_trust_digest": "bad"},
        {"release_evidence_digest": "bad"},
        {"execution_attempt_authority_digest": "bad"},
        {"created_at": -1},
        {"updated_at": -1},
        {"error_count": -1},
    ],
)
def test_finalization_dataclass_validation(kwargs):
    values = dict(
        schema_version=1,
        finalization_id="f",
        session_id="s",
        provenance_digest=fp("p"),
        phase=FinalizationPhase.STARTED,
        created_at=1.0,
        updated_at=1.0,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        AIExecutionFinalization(**values)


@pytest.mark.parametrize(
    "attempt_id,attempt_digest",
    [
        ("attempt", ""),
        ("", fp("a")),
        ("x" * 257, fp("a")),
    ],
)
def test_attempt_fields_must_be_paired(attempt_id, attempt_digest):
    with pytest.raises(ValueError):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.STARTED,
            1.0,
            1.0,
            execution_attempt_id=attempt_id,
            execution_attempt_authority_digest=attempt_digest,
        )


@pytest.mark.parametrize(
    "digest,sequence",
    [
        ("", 1),
        (fp("w"), None),
        (fp("w"), 0),
        (fp("w"), True),
    ],
)
def test_witness_fields_must_be_paired(digest, sequence):
    with pytest.raises(ValueError):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.STARTED,
            1.0,
            1.0,
            audit_witness_digest=digest,
            audit_witness_sequence=sequence,
        )


def test_session_evidence_phase_requires_digest():
    with pytest.raises(ValueError, match="session evidence"):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.SESSION_EVIDENCE,
            1.0,
            1.0,
        )


def test_checkpoint_phase_requires_checkpoint_digest():
    with pytest.raises(ValueError, match="checkpoint"):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.CHECKPOINTED,
            1.0,
            1.0,
            session_evidence_digest=fp("s"),
        )


def test_anchor_phase_requires_anchor_and_node():
    with pytest.raises(ValueError, match="anchor"):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.ANCHORED,
            1.0,
            1.0,
            session_evidence_digest=fp("s"),
            recovery_checkpoint_digest=fp("c"),
        )


def test_witness_phase_requires_witness():
    with pytest.raises(ValueError, match="witness"):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.WITNESSED,
            1.0,
            1.0,
            session_evidence_digest=fp("s"),
            recovery_checkpoint_digest=fp("c"),
            audit_anchor_digest=fp("a"),
            audit_chain_node_hash=fp("n"),
        )


def test_signed_phase_requires_signed_evidence():
    with pytest.raises(ValueError, match="signed"):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.SIGNED,
            1.0,
            1.0,
            session_evidence_digest=fp("s"),
            recovery_checkpoint_digest=fp("c"),
            audit_anchor_digest=fp("a"),
            audit_chain_node_hash=fp("n"),
        )


def test_complete_requires_anchor():
    with pytest.raises(ValueError, match="anchor"):
        AIExecutionFinalization(
            1,
            "f",
            "s",
            fp("p"),
            FinalizationPhase.COMPLETE,
            1.0,
            1.0,
            session_evidence_digest=fp("s"),
            recovery_checkpoint_digest=fp("c"),
        )


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflicted = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if not self.conflicted:
            self.conflicted = True
            raise DistributedStateConflict("synthetic race")
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(self, namespace, key, *, expected_revision):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_advance_retries_cas_conflict():
    store = AIExecutionFinalizationStore(ConflictOnceBackend())
    start = reserve(store).finalization
    stored = store.advance(
        start,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("s"),
    )
    assert stored.finalization.phase is FinalizationPhase.SESSION_EVIDENCE
    assert stored.revision == 2


class AlwaysConflictBackend(ConflictOnceBackend):
    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        raise DistributedStateConflict("always")


def test_advance_honors_retry_bound():
    store = AIExecutionFinalizationStore(
        AlwaysConflictBackend(),
        max_retries=2,
    )
    start = reserve(store).finalization
    with pytest.raises(
        ExecutionFinalizationConflict,
        match="retry bound",
    ):
        store.advance(
            start,
            FinalizationPhase.SESSION_EVIDENCE,
            session_evidence_digest=fp("s"),
        )


class CorruptValueBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(self, namespace, key, *, expected_revision):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_current_rejects_wrong_backend_value_type():
    backend = CorruptValueBackend()
    store = AIExecutionFinalizationStore(backend)
    finalization_id = "f"
    backend.put_if_absent(
        store.namespace,
        store.key(finalization_id),
        {"bad": True},
    )
    with pytest.raises(RuntimeError, match="value type"):
        store.current(finalization_id)


@pytest.mark.parametrize("retries", [0, 65, True])
def test_store_retry_bound_validation(retries):
    with pytest.raises(ValueError, match="max_retries"):
        AIExecutionFinalizationStore(
            InMemoryFencedStore(),
            max_retries=retries,
        )


def test_store_namespace_validation():
    with pytest.raises(ValueError, match="namespace"):
        AIExecutionFinalizationStore(
            InMemoryFencedStore(),
            namespace="",
        )


def test_to_dict_is_json_shaped():
    store = AIExecutionFinalizationStore(InMemoryFencedStore())
    item = reserve(store).finalization
    data = item.to_dict()
    assert data["phase"] == "started"
    assert data["recovery"] == "resume"
    assert data["binding_digest"] == item.binding_digest
    assert data["execution_attempt_id"] == "seal-1"
