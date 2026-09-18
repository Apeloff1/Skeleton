"""Rollback-resistant recovery checkpoint store tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.recovery_store import (
    AIRecoveryCheckpointStore,
    RecoveryCheckpointConflict,
    RecoveryCheckpointHead,
    RecoveryCheckpointRecord,
)
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal


def fp(char: str) -> str:
    return char * 64


def session_with_transitions(
    *,
    session_id="session",
    extra=0,
) -> AIShellSession:
    session = AIShellSession(
        session_id,
        AIIntent("intent", "recover work"),
        clock=lambda: 1.0,
    )
    if extra >= 1:
        session.transition(AISessionPhase.PLANNING)
    if extra >= 2:
        session.set_proposal(
            AIPlanProposal(
                "proposal",
                "intent",
                (AIAction("step", "python"),),
                confidence=0.9,
                uncertainty=0.1,
            )
        )
        session.transition(AISessionPhase.REVIEW)
    if extra >= 3:
        session.transition(AISessionPhase.APPROVED)
    if extra >= 4:
        session.transition(AISessionPhase.EXECUTING)
    return session


def checkpoint(
    *,
    session_id="session",
    transitions=2,
    receipt_char="r",
    release_char="l",
) -> AIRecoveryCheckpoint:
    session = session_with_transitions(
        session_id=session_id,
        extra=transitions,
    )
    base = AISessionCheckpoint.capture(
        session,
        journal_root=fp("j"),
        receipt_root=fp(receipt_char),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
    )
    return AIRecoveryCheckpoint.wrap(
        base,
        release_evidence_digest=fp(release_char),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
    )


def test_first_put_creates_item_and_session_head():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    item = checkpoint()
    committed = store.put("finalization-1", item)
    assert committed.stored.revision == 1
    assert committed.stored.record.checkpoint == item
    assert committed.head_revision == 1
    assert committed.head_advanced
    assert committed.head.finalization_id == "finalization-1"
    assert committed.head.checkpoint_digest == item.digest
    assert (
        committed.head.transition_count
        == item.session.transition_count
    )


def test_identical_put_is_idempotent():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    item = checkpoint()
    first = store.put("finalization-1", item)
    second = store.put("finalization-1", item)
    assert second.stored == first.stored
    assert second.head == first.head
    assert second.head_revision == first.head_revision
    assert not second.head_advanced


def test_same_finalization_id_rejects_different_checkpoint():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    store.put("finalization-1", checkpoint(receipt_char="a"))
    with pytest.raises(
        RecoveryCheckpointConflict,
        match="different recovery checkpoint",
    ):
        store.put(
            "finalization-1",
            checkpoint(receipt_char="b"),
        )


def test_newer_transition_advances_session_head():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    first = checkpoint(transitions=1)
    second = checkpoint(transitions=2)
    store.put("first", first)
    committed = store.put("second", second)
    assert committed.head_advanced
    assert committed.head.finalization_id == "second"
    assert committed.head.transition_count > first.session.transition_count
    current = store.current_session("session")
    assert current.record.checkpoint.digest == second.digest


def test_older_transition_is_persisted_without_rolling_back_head():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    newer = checkpoint(transitions=3)
    older = checkpoint(transitions=1)
    first = store.put("newer", newer)
    second = store.put("older", older)
    assert not second.head_advanced
    assert second.head.finalization_id == "newer"
    assert store.get("older").record.checkpoint.digest == older.digest
    assert (
        store.current_session("session").record.checkpoint.digest
        == newer.digest
    )
    assert second.head_revision == first.head_revision


def test_same_transition_count_conflicting_checkpoint_is_rejected():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    first = checkpoint(
        transitions=2,
        receipt_char="a",
    )
    second = checkpoint(
        transitions=2,
        receipt_char="b",
    )
    store.put("one", first)
    with pytest.raises(
        RecoveryCheckpointConflict,
        match="same session transition count",
    ):
        store.put("two", second)


def test_different_sessions_have_independent_heads():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    one = checkpoint(session_id="one", transitions=1)
    two = checkpoint(session_id="two", transitions=3)
    store.put("f-one", one)
    store.put("f-two", two)
    assert (
        store.current_session("one").record.checkpoint.digest
        == one.digest
    )
    assert (
        store.current_session("two").record.checkpoint.digest
        == two.digest
    )


def test_require_exact_checkpoint_digest():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    item = checkpoint()
    store.put("f", item)
    assert store.require(
        "f",
        checkpoint_digest=item.digest,
    ).record.checkpoint == item
    with pytest.raises(
        RecoveryCheckpointConflict,
        match="digest mismatch",
    ):
        store.require(
            "f",
            checkpoint_digest=fp("x"),
        )


def test_require_missing_checkpoint():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    with pytest.raises(
        RecoveryCheckpointConflict,
        match="missing",
    ):
        store.require("missing")


def test_verify_session_head():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    assert not store.verify_session_head("session")
    store.put("f", checkpoint())
    assert store.verify_session_head("session")


def test_record_digest_changes_with_checkpoint():
    first = RecoveryCheckpointRecord(
        "f",
        "session",
        checkpoint(receipt_char="a"),
        1.0,
    )
    second = RecoveryCheckpointRecord(
        "f",
        "session",
        checkpoint(receipt_char="b"),
        1.0,
    )
    assert first.digest != second.digest


def test_record_digest_changes_with_finalization_id():
    item = checkpoint()
    first = RecoveryCheckpointRecord(
        "a",
        "session",
        item,
        1.0,
    )
    second = RecoveryCheckpointRecord(
        "b",
        "session",
        item,
        1.0,
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"finalization_id": ""},
        {"session_id": ""},
        {"stored_at": -1},
        {"stored_at": float("inf")},
    ],
)
def test_record_validation(kwargs):
    values = dict(
        finalization_id="f",
        session_id="session",
        checkpoint=checkpoint(),
        stored_at=1.0,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        RecoveryCheckpointRecord(**values)


def test_record_rejects_session_mismatch():
    with pytest.raises(ValueError, match="binding"):
        RecoveryCheckpointRecord(
            "f",
            "other",
            checkpoint(session_id="session"),
            1.0,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"session_id": ""},
        {"finalization_id": ""},
        {"checkpoint_digest": "bad"},
        {"transition_count": -1},
        {"transition_count": True},
    ],
)
def test_head_validation(kwargs):
    values = dict(
        session_id="session",
        finalization_id="f",
        checkpoint_digest=fp("c"),
        transition_count=1,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        RecoveryCheckpointHead(**values)


def test_item_key_hides_finalization_id():
    key = AIRecoveryCheckpointStore._item_key(
        "sensitive-finalization-id"
    )
    assert key.startswith("item:")
    assert "sensitive-finalization-id" not in key
    assert key == AIRecoveryCheckpointStore._item_key(
        "sensitive-finalization-id"
    )


def test_head_key_hides_session_id():
    key = AIRecoveryCheckpointStore._head_key(
        "sensitive-session"
    )
    assert key.startswith("head:")
    assert "sensitive-session" not in key
    assert key == AIRecoveryCheckpointStore._head_key(
        "sensitive-session"
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
            raise DistributedStateConflict("synthetic head race")
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


def test_head_update_retries_cas_conflict():
    backend = ConflictOnceBackend()
    store = AIRecoveryCheckpointStore(backend)
    store.put("first", checkpoint(transitions=1))
    committed = store.put(
        "second",
        checkpoint(transitions=2),
    )
    assert committed.head.finalization_id == "second"
    assert committed.head_advanced


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


def test_head_update_honors_retry_bound():
    backend = AlwaysConflictBackend()
    store = AIRecoveryCheckpointStore(
        backend,
        max_retries=2,
    )
    store.put("first", checkpoint(transitions=1))
    with pytest.raises(
        RecoveryCheckpointConflict,
        match="retry bound",
    ):
        store.put(
            "second",
            checkpoint(transitions=2),
        )


def test_current_session_detects_missing_item():
    backend = InMemoryFencedStore()
    store = AIRecoveryCheckpointStore(backend)
    item = checkpoint()
    store.put("f", item)
    item_key = store._item_key("f")
    record = backend.get(store.namespace, item_key)
    backend.delete(
        store.namespace,
        item_key,
        expected_revision=record.revision,
    )
    with pytest.raises(RuntimeError, match="missing item"):
        store.current_session("session")


def test_current_session_detects_head_digest_tamper():
    backend = InMemoryFencedStore()
    store = AIRecoveryCheckpointStore(backend)
    store.put("f", checkpoint())
    head_key = store._head_key("session")
    record = backend.get(store.namespace, head_key)
    tampered = replace(
        record.value,
        checkpoint_digest=fp("x"),
    )
    backend.compare_and_swap(
        store.namespace,
        head_key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(RuntimeError, match="digest mismatch"):
        store.current_session("session")


def test_get_rejects_wrong_backend_value_type():
    backend = InMemoryFencedStore()
    store = AIRecoveryCheckpointStore(backend)
    backend.put_if_absent(
        store.namespace,
        store._item_key("f"),
        {"bad": True},
    )
    with pytest.raises(RuntimeError, match="value type"):
        store.get("f")


def test_head_rejects_wrong_backend_value_type():
    backend = InMemoryFencedStore()
    store = AIRecoveryCheckpointStore(backend)
    backend.put_if_absent(
        store.namespace,
        store._head_key("session"),
        {"bad": True},
    )
    with pytest.raises(RuntimeError, match="head type"):
        store.head("session")


def test_put_rejects_non_checkpoint():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    with pytest.raises(TypeError, match="AIRecoveryCheckpoint"):
        store.put("f", object())


@pytest.mark.parametrize("retries", [0, 65, True])
def test_retry_bound_validation(retries):
    with pytest.raises(ValueError, match="max_retries"):
        AIRecoveryCheckpointStore(
            InMemoryFencedStore(),
            max_retries=retries,
        )


def test_namespace_validation():
    with pytest.raises(ValueError, match="namespace"):
        AIRecoveryCheckpointStore(
            InMemoryFencedStore(),
            namespace="",
        )


def test_commit_to_dict_is_json_shaped():
    store = AIRecoveryCheckpointStore(InMemoryFencedStore())
    committed = store.put("f", checkpoint())
    data = committed.to_dict()
    assert data["record"]["finalization_id"] == "f"
    assert data["head"]["session_id"] == "session"
    assert data["head_advanced"] is True
