"""Durable finalized session-journal manifest tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalCommit,
    DurableSessionJournalConflict,
    DurableSessionJournalCorruption,
    DurableSessionJournalHead,
    DurableSessionJournalManifest,
    DurableSessionJournalStore,
    StoredDurableSessionJournal,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvidence,
)


def fp(char: str) -> str:
    return char * 64


def journal_with_session(
    *,
    session_id="session",
    events=3,
    other_events=0,
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    for index in range(events):
        journal.append(
            f"session.event.{index}",
            session_id=session_id,
            intent_id="intent",
            proposal_id="proposal",
            summary=f"event {index}",
        )
    for index in range(other_events):
        journal.append(
            f"other.event.{index}",
            session_id="other",
            intent_id="other-intent",
            proposal_id="other-proposal",
            summary=f"other {index}",
        )
    evidence = SessionJournalEvidence.from_journal(
        journal,
        session_id,
    )
    return backend, journal, evidence


def make_store(
    backend=None,
    *,
    namespace="manifests",
    clock=lambda: 20.0,
    max_events_per_manifest=16_384,
    max_retries=16,
):
    return DurableSessionJournalStore(
        backend or InMemoryFencedStore(),
        namespace=namespace,
        clock=clock,
        max_events_per_manifest=max_events_per_manifest,
        max_retries=max_retries,
    )


def test_manifest_captures_projection_metadata():
    _, journal, evidence = journal_with_session(
        events=3,
        other_events=2,
    )
    manifest = DurableSessionJournalManifest(
        1,
        "finalization",
        "session",
        journal.root_hash(),
        evidence,
        20.0,
    )
    assert manifest.event_count == 3
    assert manifest.first_sequence == 1
    assert manifest.last_sequence == 3
    assert manifest.journal_digest == evidence.digest
    assert len(manifest.digest) == 64
    data = manifest.to_dict()
    assert data["finalization_id"] == "finalization"
    assert data["session_id"] == "session"
    assert data["event_count"] == 3
    assert data["journal_digest"] == evidence.digest
    assert data["digest"] == manifest.digest


def test_empty_manifest_has_no_sequence_bounds():
    evidence = SessionJournalEvidence(
        "session",
        (),
    )
    manifest = DurableSessionJournalManifest(
        1,
        "finalization",
        "session",
        fp("a"),
        evidence,
        1.0,
    )
    assert manifest.event_count == 0
    assert manifest.first_sequence is None
    assert manifest.last_sequence is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"finalization_id": ""},
        {"session_id": ""},
        {"journal_root": "bad"},
        {"stored_at": -1},
        {"stored_at": float("nan")},
        {"stored_at": float("inf")},
    ],
)
def test_manifest_validation(kwargs):
    evidence = SessionJournalEvidence(
        "session",
        (),
    )
    values = dict(
        schema_version=1,
        finalization_id="finalization",
        session_id="session",
        journal_root=fp("a"),
        journal_evidence=evidence,
        stored_at=1.0,
    )
    values.update(kwargs)
    with pytest.raises(
        (ValueError, TypeError)
    ):
        DurableSessionJournalManifest(
            **values
        )


def test_manifest_rejects_session_mismatch():
    with pytest.raises(
        ValueError,
        match="session binding",
    ):
        DurableSessionJournalManifest(
            1,
            "finalization",
            "session",
            fp("a"),
            SessionJournalEvidence(
                "other",
                (),
            ),
            1.0,
        )


def test_manifest_requires_evidence_type():
    with pytest.raises(TypeError):
        DurableSessionJournalManifest(
            1,
            "finalization",
            "session",
            fp("a"),
            object(),
            1.0,
        )


def test_head_captures_latest_manifest_identity():
    head = DurableSessionJournalHead(
        "session",
        "finalization",
        fp("a"),
        fp("b"),
        3,
        7,
    )
    assert head.to_dict() == {
        "session_id": "session",
        "finalization_id": "finalization",
        "journal_root": fp("a"),
        "journal_digest": fp("b"),
        "event_count": 3,
        "last_sequence": 7,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"session_id": ""},
        {"finalization_id": ""},
        {"journal_root": "bad"},
        {"journal_digest": "bad"},
        {"event_count": -1},
        {"event_count": True},
        {"last_sequence": 0},
        {"last_sequence": True},
    ],
)
def test_head_validation(kwargs):
    values = dict(
        session_id="session",
        finalization_id="finalization",
        journal_root=fp("a"),
        journal_digest=fp("b"),
        event_count=1,
        last_sequence=1,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableSessionJournalHead(
            **values
        )


def test_head_empty_count_requires_absent_last_sequence():
    with pytest.raises(
        ValueError,
        match="presence mismatch",
    ):
        DurableSessionJournalHead(
            "session",
            "finalization",
            fp("a"),
            fp("b"),
            0,
            1,
        )
    with pytest.raises(
        ValueError,
        match="presence mismatch",
    ):
        DurableSessionJournalHead(
            "session",
            "finalization",
            fp("a"),
            fp("b"),
            1,
            None,
        )


def test_first_put_creates_manifest_and_head():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    commit = store.put(
        finalization_id="finalization",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    assert isinstance(
        commit,
        DurableSessionJournalCommit,
    )
    assert commit.stored.revision == 1
    assert commit.head_revision == 1
    assert commit.head_advanced
    assert (
        commit.stored.manifest.journal_digest
        == evidence.digest
    )
    assert (
        commit.head.finalization_id
        == "finalization"
    )


def test_identical_put_is_idempotent():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    first = store.put(
        finalization_id="finalization",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    second = store.put(
        finalization_id="finalization",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    assert second.stored == first.stored
    assert (
        second.head_revision
        == first.head_revision
    )
    assert not second.head_advanced


def test_same_finalization_rejects_different_projection():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="finalization",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    journal.append(
        "session.extra",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    changed = SessionJournalEvidence.from_journal(
        journal,
        "session",
    )
    with pytest.raises(
        DurableSessionJournalConflict,
        match="different",
    ):
        store.put(
            finalization_id="finalization",
            journal_root=journal.root_hash(),
            journal_evidence=changed,
        )


def test_newer_session_projection_advances_head():
    backend, journal, first_evidence = (
        journal_with_session(
            events=1
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    first = store.put(
        finalization_id="first",
        journal_root=journal.root_hash(),
        journal_evidence=first_evidence,
    )
    journal.append(
        "session.second",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    second_evidence = (
        SessionJournalEvidence.from_journal(
            journal,
            "session",
        )
    )
    second = store.put(
        finalization_id="second",
        journal_root=journal.root_hash(),
        journal_evidence=second_evidence,
    )
    assert first.head_advanced
    assert second.head_advanced
    assert second.head.finalization_id == "second"
    assert second.head.last_sequence == 2
    current = store.current_session(
        "session"
    )
    assert (
        current.manifest.finalization_id
        == "second"
    )


def test_older_manifest_does_not_roll_back_head():
    backend, journal, first_evidence = (
        journal_with_session(
            events=1
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    first_root = journal.root_hash()
    journal.append(
        "session.second",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    newer = (
        SessionJournalEvidence.from_journal(
            journal,
            "session",
        )
    )
    latest = store.put(
        finalization_id="newer",
        journal_root=journal.root_hash(),
        journal_evidence=newer,
    )
    old = store.put(
        finalization_id="older",
        journal_root=first_root,
        journal_evidence=first_evidence,
    )
    assert not old.head_advanced
    assert (
        old.head.finalization_id
        == latest.head.finalization_id
    )
    assert (
        store.current_session(
            "session"
        ).manifest.finalization_id
        == "newer"
    )
    assert (
        store.get("older")
        .manifest.journal_digest
        == first_evidence.digest
    )


def test_same_last_sequence_conflict_is_rejected():
    backend, journal, evidence = (
        journal_with_session(
            events=1
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="first",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    conflicting = replace(
        evidence,
        events=(
            replace(
                evidence.events[0],
                kind="different.kind",
            ),
        ),
    )
    with pytest.raises(
        DurableSessionJournalConflict,
        match="conflicting manifest",
    ):
        store.put(
            finalization_id="second",
            journal_root=journal.root_hash(),
            journal_evidence=conflicting,
        )


def test_different_sessions_have_independent_heads():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    journal.append(
        "one",
        session_id="one",
        intent_id="intent-one",
    )
    evidence_one = (
        SessionJournalEvidence.from_journal(
            journal,
            "one",
        )
    )
    root_one = journal.root_hash()
    journal.append(
        "two",
        session_id="two",
        intent_id="intent-two",
    )
    evidence_two = (
        SessionJournalEvidence.from_journal(
            journal,
            "two",
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="f-one",
        journal_root=root_one,
        journal_evidence=evidence_one,
    )
    store.put(
        finalization_id="f-two",
        journal_root=journal.root_hash(),
        journal_evidence=evidence_two,
    )
    assert (
        store.current_session("one")
        .manifest.session_id
        == "one"
    )
    assert (
        store.current_session("two")
        .manifest.session_id
        == "two"
    )


def test_require_checks_journal_digest():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    assert (
        store.require(
            "f",
            journal_digest=evidence.digest,
        ).manifest.journal_digest
        == evidence.digest
    )
    with pytest.raises(
        DurableSessionJournalConflict,
        match="digest mismatch",
    ):
        store.require(
            "f",
            journal_digest=fp("f"),
        )


def test_require_checks_journal_root():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    root = journal.root_hash()
    store.put(
        finalization_id="f",
        journal_root=root,
        journal_evidence=evidence,
    )
    assert (
        store.require(
            "f",
            journal_root=root,
        ).manifest.journal_root
        == root
    )
    with pytest.raises(
        DurableSessionJournalConflict,
        match="root mismatch",
    ):
        store.require(
            "f",
            journal_root=fp("f"),
        )


def test_require_missing_manifest():
    store = make_store()
    with pytest.raises(
        DurableSessionJournalConflict,
        match="missing",
    ):
        store.require("missing")


def test_get_missing_returns_none():
    assert (
        make_store().get(
            "missing"
        )
        is None
    )


def test_head_missing_returns_none():
    assert (
        make_store().head(
            "missing"
        )
        is None
    )


def test_current_session_missing_returns_none():
    assert (
        make_store().current_session(
            "missing"
        )
        is None
    )


def test_manifest_key_hides_finalization_id():
    key = (
        DurableSessionJournalStore
        ._manifest_key(
            "sensitive-finalization"
        )
    )
    assert key.startswith("manifest:")
    assert "sensitive" not in key
    assert key == (
        DurableSessionJournalStore
        ._manifest_key(
            "sensitive-finalization"
        )
    )


def test_head_key_hides_session_id():
    key = (
        DurableSessionJournalStore
        ._head_key(
            "sensitive-session"
        )
    )
    assert key.startswith("head:")
    assert "sensitive" not in key


def test_event_bound_is_enforced():
    backend, journal, evidence = (
        journal_with_session(
            events=2
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
        max_events_per_manifest=1,
    )
    with pytest.raises(
        DurableSessionJournalConflict,
        match="event bound",
    ):
        store.put(
            finalization_id="f",
            journal_root=journal.root_hash(),
            journal_evidence=evidence,
        )


def test_put_requires_session_journal_type():
    store = make_store()
    with pytest.raises(TypeError):
        store.put(
            finalization_id="f",
            journal_root=fp("a"),
            journal_evidence=object(),
        )


def test_store_namespace_validation():
    with pytest.raises(ValueError):
        make_store(namespace="")
    with pytest.raises(ValueError):
        make_store(namespace="x" * 129)


@pytest.mark.parametrize(
    "maximum",
    [0, -1, True, 1.5],
)
def test_store_event_bound_validation(maximum):
    with pytest.raises(ValueError):
        make_store(
            max_events_per_manifest=maximum
        )


@pytest.mark.parametrize(
    "retries",
    [0, 65, True, 1.5],
)
def test_store_retry_validation(retries):
    with pytest.raises(ValueError):
        make_store(
            max_retries=retries
        )


def test_store_clock_must_be_callable():
    with pytest.raises(TypeError):
        make_store(
            clock=object()
        )


def test_wrong_manifest_backend_type_is_corruption():
    backend = InMemoryFencedStore()
    store = make_store(
        backend,
        namespace="manifests",
    )
    backend.put_if_absent(
        "manifests",
        store._manifest_key("f"),
        {"bad": True},
    )
    with pytest.raises(
        DurableSessionJournalCorruption,
        match="manifest",
    ):
        store.get("f")


def test_wrong_head_backend_type_is_corruption():
    backend = InMemoryFencedStore()
    store = make_store(
        backend,
        namespace="manifests",
    )
    backend.put_if_absent(
        "manifests",
        store._head_key("session"),
        {"bad": True},
    )
    with pytest.raises(
        DurableSessionJournalCorruption,
        match="head",
    ):
        store.head("session")


def test_current_session_detects_missing_manifest():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    commit = store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    manifest_key = store._manifest_key(
        "f"
    )
    record = backend.get(
        "manifests",
        manifest_key,
    )
    backend.delete(
        "manifests",
        manifest_key,
        expected_revision=record.revision,
    )
    assert commit.head.finalization_id == "f"
    with pytest.raises(
        DurableSessionJournalCorruption,
        match="missing manifest",
    ):
        store.current_session("session")


def test_current_session_detects_pointer_tamper():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    head_key = store._head_key(
        "session"
    )
    record = backend.get(
        "manifests",
        head_key,
    )
    backend.compare_and_swap(
        "manifests",
        head_key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            journal_digest=fp("f"),
        ),
    )
    with pytest.raises(
        DurableSessionJournalCorruption,
        match="mismatch",
    ):
        store.current_session("session")


def test_verify_manifest_against_authoritative_journal():
    backend, journal, evidence = (
        journal_with_session(
            events=3,
            other_events=2,
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    assert store.verify_manifest(
        "f",
        journal=journal,
    )


def test_verify_manifest_survives_later_unrelated_events():
    backend, journal, evidence = (
        journal_with_session(
            events=3
        )
    )
    root = journal.root_hash()
    store = make_store(
        backend,
        namespace="manifests",
    )
    store.put(
        finalization_id="f",
        journal_root=root,
        journal_evidence=evidence,
    )
    for index in range(10):
        journal.append(
            f"other.{index}",
            session_id="other",
            intent_id="other",
        )
    assert journal.root_hash() != root
    assert store.verify_manifest(
        "f",
        journal=journal,
    )


def test_verify_manifest_rejects_event_substitution():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    commit = store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    key = store._manifest_key("f")
    record = backend.get(
        "manifests",
        key,
    )
    bad_evidence = replace(
        evidence,
        events=(
            replace(
                evidence.events[0],
                event_hash=fp("f"),
            ),
            *evidence.events[1:],
        ),
    )
    bad_manifest = replace(
        commit.stored.manifest,
        journal_evidence=bad_evidence,
    )
    backend.compare_and_swap(
        "manifests",
        key,
        expected_revision=record.revision,
        value=bad_manifest,
    )
    assert not store.verify_manifest(
        "f",
        journal=journal,
    )


def test_verify_manifest_missing_returns_false():
    _, journal, _ = (
        journal_with_session()
    )
    store = make_store()
    assert not store.verify_manifest(
        "missing",
        journal=journal,
    )


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflicted = False

    def get(self, namespace, key):
        return self.store.get(
            namespace,
            key,
        )

    def put_if_absent(
        self,
        namespace,
        key,
        value,
    ):
        return self.store.put_if_absent(
            namespace,
            key,
            value,
        )

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            key.startswith("head:")
            and not self.conflicted
        ):
            self.conflicted = True
            raise DistributedStateConflict(
                "synthetic race"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_head_update_retries_cas_conflict():
    backend = ConflictOnceBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    journal.append(
        "one",
        session_id="session",
        intent_id="intent",
    )
    evidence = (
        SessionJournalEvidence.from_journal(
            journal,
            "session",
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    commit = store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    assert commit.head_advanced
    assert commit.head_revision == 1


class AlwaysConflictBackend(
    ConflictOnceBackend
):
    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if key.startswith("head:"):
            raise DistributedStateConflict(
                "always"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_head_update_honors_retry_bound():
    backend = AlwaysConflictBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    journal.append(
        "one",
        session_id="session",
        intent_id="intent",
    )
    evidence = (
        SessionJournalEvidence.from_journal(
            journal,
            "session",
        )
    )
    store = make_store(
        backend,
        namespace="manifests",
        max_retries=2,
    )
    # Creating a missing head uses put_if_absent and does not need CAS.
    first = store.put(
        finalization_id="first",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    assert first.head_advanced

    journal.append(
        "two",
        session_id="session",
        intent_id="intent",
    )
    newer = (
        SessionJournalEvidence.from_journal(
            journal,
            "session",
        )
    )
    with pytest.raises(
        DurableSessionJournalConflict,
        match="retry bound",
    ):
        store.put(
            finalization_id="second",
            journal_root=journal.root_hash(),
            journal_evidence=newer,
        )


def test_stored_wrapper_validation():
    _, journal, evidence = (
        journal_with_session()
    )
    manifest = DurableSessionJournalManifest(
        1,
        "f",
        "session",
        journal.root_hash(),
        evidence,
        1.0,
    )
    with pytest.raises(ValueError):
        StoredDurableSessionJournal(
            0,
            manifest,
        )


def test_commit_validation():
    _, journal, evidence = (
        journal_with_session()
    )
    manifest = DurableSessionJournalManifest(
        1,
        "f",
        "session",
        journal.root_hash(),
        evidence,
        1.0,
    )
    stored = StoredDurableSessionJournal(
        1,
        manifest,
    )
    head = DurableSessionJournalHead(
        "session",
        "f",
        journal.root_hash(),
        evidence.digest,
        len(evidence.events),
        evidence.events[-1].global_sequence,
    )
    with pytest.raises(ValueError):
        DurableSessionJournalCommit(
            stored,
            0,
            head,
            True,
        )
    with pytest.raises(ValueError):
        DurableSessionJournalCommit(
            stored,
            1,
            head,
            "yes",
        )


def test_commit_to_dict_contains_manifest_and_head():
    backend, journal, evidence = (
        journal_with_session()
    )
    store = make_store(
        backend,
        namespace="manifests",
    )
    commit = store.put(
        finalization_id="f",
        journal_root=journal.root_hash(),
        journal_evidence=evidence,
    )
    data = commit.to_dict()
    assert data["stored"]["manifest"]["finalization_id"] == "f"
    assert data["head"]["session_id"] == "session"
    assert data["head_advanced"] is True
