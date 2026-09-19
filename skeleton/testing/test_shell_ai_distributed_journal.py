"""Distributed AI decision journal concurrency and corruption tests."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalConflict,
    DistributedJournalCorruption,
    DistributedJournalHead,
    GENESIS_HASH,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
)


def event_hash(
    previous: str,
    sequence: int,
    *,
    kind: str = "test.event",
    observed_at: float = 1.0,
    session_id: str = "session",
    intent_id: str = "intent",
    proposal_id: str = "proposal",
    summary: str = "summary",
    data=None,
) -> str:
    return AIDecisionJournal._hash(
        previous,
        sequence,
        kind,
        observed_at,
        session_id,
        intent_id,
        proposal_id,
        summary,
        data or {},
    )


def append_one(
    journal: DistributedAIDecisionJournal,
    *,
    kind="test.event",
    session_id="session",
    intent_id="intent",
    proposal_id="proposal",
    summary="summary",
    data=None,
):
    return journal.append(
        kind,
        session_id=session_id,
        intent_id=intent_id,
        proposal_id=proposal_id,
        summary=summary,
        data=data,
    )


def test_empty_journal_uses_genesis():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    assert journal.snapshot() == ()
    assert journal.length() == 0
    assert journal.root_hash() == GENESIS_HASH
    assert journal.verify()
    assert journal.head() == DistributedJournalHead(
        0,
        GENESIS_HASH,
    )


def test_append_preserves_local_journal_hash_contract():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 10.0,
    )
    event = append_one(
        journal,
        data={"value": 1},
    )
    expected = AIDecisionJournal._hash(
        GENESIS_HASH,
        1,
        "test.event",
        10.0,
        "session",
        "intent",
        "proposal",
        "summary",
        {"value": 1},
    )
    assert event.event_hash == expected
    assert event.previous_hash == GENESIS_HASH
    assert event.sequence == 1
    assert journal.root_hash() == expected
    assert journal.verify()


def test_multiple_appends_form_contiguous_chain():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 2.0,
    )
    first = append_one(
        journal,
        kind="one",
        proposal_id="p1",
    )
    second = append_one(
        journal,
        kind="two",
        proposal_id="p2",
    )
    third = append_one(
        journal,
        kind="three",
        proposal_id="p3",
    )
    assert journal.snapshot() == (
        first,
        second,
        third,
    )
    assert second.previous_hash == first.event_hash
    assert third.previous_hash == second.event_hash
    assert journal.head().sequence == 3
    assert journal.root_hash() == third.event_hash
    assert journal.verify()


def test_fresh_reader_observes_same_chain():
    backend = InMemoryFencedStore()
    writer = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 3.0,
    )
    first = append_one(writer, kind="one")
    second = append_one(writer, kind="two")

    reader = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 99.0,
    )
    assert reader.snapshot() == (first, second)
    assert reader.root_hash() == writer.root_hash()
    assert reader.verify()


def test_events_for_session_filters_without_reordering():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 4.0,
    )
    first = append_one(
        journal,
        session_id="a",
        proposal_id="a1",
    )
    append_one(
        journal,
        session_id="b",
        proposal_id="b1",
    )
    third = append_one(
        journal,
        session_id="a",
        proposal_id="a2",
    )
    assert journal.events_for_session("a") == (
        first,
        third,
    )


def test_require_root_accepts_current_verified_root():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 5.0,
    )
    append_one(journal)
    head = journal.require_root(
        journal.root_hash()
    )
    assert head == journal.head()


def test_require_root_rejects_other_root():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DistributedJournalConflict,
        match="differs",
    ):
        journal.require_root("f" * 64)


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_namespace_validation(namespace):
    with pytest.raises(ValueError, match="namespace"):
        DistributedAIDecisionJournal(
            InMemoryFencedStore(),
            namespace=namespace,
        )


@pytest.mark.parametrize(
    "max_events",
    [0, -1, True, 1.2],
)
def test_max_events_validation(max_events):
    with pytest.raises(ValueError, match="max_events"):
        DistributedAIDecisionJournal(
            InMemoryFencedStore(),
            max_events=max_events,
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True, 1.5],
)
def test_retry_bound_validation(retries):
    with pytest.raises(ValueError, match="max_cas_retries"):
        DistributedAIDecisionJournal(
            InMemoryFencedStore(),
            max_cas_retries=retries,
        )


def test_clock_must_be_callable():
    with pytest.raises(TypeError, match="clock"):
        DistributedAIDecisionJournal(
            InMemoryFencedStore(),
            clock=object(),
        )


@pytest.mark.parametrize(
    "clock_value",
    [-1.0, float("nan"), float("inf"), True, "now"],
)
def test_append_rejects_invalid_clock(clock_value):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: clock_value,
    )
    with pytest.raises(ValueError, match="clock"):
        append_one(journal)


@pytest.mark.parametrize(
    "kind",
    ["", "x" * 129],
)
def test_append_kind_validation(kind):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="kind"):
        append_one(journal, kind=kind)


@pytest.mark.parametrize(
    "session_id",
    ["", "x" * 161],
)
def test_append_session_validation(session_id):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="session_id"):
        append_one(
            journal,
            session_id=session_id,
        )


@pytest.mark.parametrize(
    "intent_id",
    ["", "x" * 161],
)
def test_append_intent_validation(intent_id):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="intent_id"):
        append_one(
            journal,
            intent_id=intent_id,
        )


def test_append_proposal_validation():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="proposal_id"):
        append_one(
            journal,
            proposal_id="x" * 161,
        )


def test_append_summary_validation():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="summary"):
        append_one(
            journal,
            summary="x" * 2049,
        )


def test_append_data_field_bound():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="data fields"):
        append_one(
            journal,
            data={
                f"k{i}": i
                for i in range(129)
            },
        )


def test_capacity_exhaustion():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        max_events=1,
        clock=lambda: 6.0,
    )
    append_one(journal)
    with pytest.raises(RuntimeError, match="capacity"):
        append_one(journal)


def test_get_event_rejects_bad_hash_shape():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="SHA-256"):
        journal.get_event("bad")


def test_events_for_session_validates_identity():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="session_id"):
        journal.events_for_session("")


def test_head_validation():
    with pytest.raises(ValueError):
        DistributedJournalHead(-1, GENESIS_HASH)
    with pytest.raises(ValueError):
        DistributedJournalHead(0, "f" * 64)
    with pytest.raises(ValueError):
        DistributedJournalHead(1, GENESIS_HASH)
    with pytest.raises(ValueError):
        DistributedJournalHead(1, "bad")


def test_wrong_head_type_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "journal",
        "head",
        {"bad": True},
    )
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="head",
    ):
        journal.head()
    assert not journal.verify()


def test_missing_committed_event_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "journal",
        "head",
        DistributedJournalHead(
            1,
            "f" * 64,
        ),
    )
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="missing",
    ):
        journal.snapshot()
    assert not journal.verify()


def test_wrong_event_value_type_is_corruption():
    backend = InMemoryFencedStore()
    event_hash_value = "a" * 64
    backend.put_if_absent(
        "journal",
        f"event:{event_hash_value}",
        {"bad": True},
    )
    backend.put_if_absent(
        "journal",
        "head",
        DistributedJournalHead(
            1,
            event_hash_value,
        ),
    )
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="value type",
    ):
        journal.snapshot()


def test_event_payload_tamper_breaks_verification():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 7.0,
    )
    event = append_one(
        journal,
        data={"safe": True},
    )
    key = journal._event_key(event.event_hash)
    record = backend.get("journal", key)
    tampered = replace(
        event,
        summary="tampered",
    )
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    assert not journal.verify()
    with pytest.raises(
        DistributedJournalCorruption,
        match="digest",
    ):
        journal.snapshot()


def test_event_key_hash_mismatch_is_corruption():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 8.0,
    )
    event = append_one(journal)
    fake = "f" * 64
    backend.put_if_absent(
        "journal",
        f"event:{fake}",
        event,
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="key/hash",
    ):
        journal.get_event(fake)


class CompetingWriterBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.injected = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
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
            key == "head"
            and not self.injected
            and expected_revision == 0
        ):
            self.injected = True
            payload = MappingProxyType(
                {"writer": "competitor"}
            )
            digest = AIDecisionJournal._hash(
                GENESIS_HASH,
                1,
                "race.competitor",
                1.0,
                "other-session",
                "other-intent",
                "",
                "competitor",
                payload,
            )
            event = AIDecisionEvent(
                1,
                GENESIS_HASH,
                digest,
                "race.competitor",
                1.0,
                "other-session",
                "other-intent",
                "",
                "competitor",
                payload,
            )
            self.store.put_if_absent(
                namespace,
                f"event:{digest}",
                event,
            )
            self.store.compare_and_swap(
                namespace,
                "head",
                expected_revision=0,
                value=DistributedJournalHead(
                    1,
                    digest,
                ),
            )
            raise DistributedStateConflict(
                "synthetic competing writer"
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


def test_competing_writer_is_serialized_by_head_cas():
    backend = CompetingWriterBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 2.0,
    )
    ours = append_one(
        journal,
        kind="race.ours",
        session_id="ours",
    )
    items = journal.snapshot()
    assert len(items) == 2
    assert items[0].kind == "race.competitor"
    assert items[1] == ours
    assert ours.sequence == 2
    assert journal.verify()


def test_lost_cas_candidate_remains_unreachable():
    backend = CompetingWriterBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 2.0,
    )
    ours = append_one(
        journal,
        kind="race.ours",
        session_id="ours",
    )
    orphan_hash = AIDecisionJournal._hash(
        GENESIS_HASH,
        1,
        "race.ours",
        2.0,
        "ours",
        "intent",
        "proposal",
        "summary",
        {},
    )
    orphan = journal.get_event(orphan_hash)
    assert orphan.sequence == 1
    assert orphan.event_hash not in {
        item.event_hash
        for item in journal.snapshot()
    }
    assert ours.sequence == 2


class SameStateConflictBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
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
        if key == "head":
            raise DistributedStateConflict(
                "synthetic unexplained conflict"
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


def test_same_state_cas_conflict_is_not_silently_retried():
    journal = DistributedAIDecisionJournal(
        SameStateConflictBackend(),
        namespace="journal",
        clock=lambda: 9.0,
    )
    with pytest.raises(
        DistributedStateConflict,
        match="synthetic",
    ):
        append_one(journal)


def test_data_is_immutable_after_append():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 10.0,
    )
    source = {"value": 1}
    event = append_one(
        journal,
        data=source,
    )
    source["value"] = 2
    assert event.data["value"] == 1
    with pytest.raises(TypeError):
        event.data["value"] = 3


def test_head_to_dict():
    head = DistributedJournalHead(
        2,
        "a" * 64,
    )
    assert head.to_dict() == {
        "sequence": 2,
        "root_hash": "a" * 64,
    }


def test_reader_namespace_isolation():
    backend = InMemoryFencedStore()
    first = DistributedAIDecisionJournal(
        backend,
        namespace="first",
        clock=lambda: 1.0,
    )
    second = DistributedAIDecisionJournal(
        backend,
        namespace="second",
        clock=lambda: 1.0,
    )
    append_one(first, session_id="one")
    append_one(second, session_id="two")
    assert first.length() == 1
    assert second.length() == 1
    assert (
        first.snapshot()[0].session_id
        == "one"
    )
    assert (
        second.snapshot()[0].session_id
        == "two"
    )

def test_snapshot_at_genesis_is_empty():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    assert journal.snapshot_at(GENESIS_HASH) == ()
    assert journal.verify_root(GENESIS_HASH)
    assert journal.root_is_ancestor(GENESIS_HASH)


def test_snapshot_at_historical_root_returns_exact_prefix():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 11.0,
    )
    first = append_one(journal, kind="first")
    second = append_one(journal, kind="second")
    append_one(journal, kind="third")
    assert journal.snapshot_at(
        first.event_hash
    ) == (first,)
    assert journal.snapshot_at(
        second.event_hash
    ) == (first, second)
    assert journal.verify_root(
        first.event_hash
    )
    assert journal.root_is_ancestor(
        first.event_hash
    )


def test_verify_root_rejects_missing_hash():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    assert not journal.verify_root("f" * 64)
    assert not journal.root_is_ancestor("f" * 64)


def test_historical_session_filter_stops_at_requested_root():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 12.0,
    )
    first = append_one(
        journal,
        kind="first",
        session_id="session",
    )
    cutoff = append_one(
        journal,
        kind="cutoff",
        session_id="other",
    )
    append_one(
        journal,
        kind="later",
        session_id="session",
    )
    historical = journal.events_for_session(
        "session",
        root_hash=cutoff.event_hash,
    )
    assert historical == (first,)


def test_self_consistent_orphan_root_is_not_committed_ancestor():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 13.0,
    )
    committed = append_one(journal)
    payload = MappingProxyType({})
    orphan_hash = AIDecisionJournal._hash(
        committed.event_hash,
        2,
        "orphan",
        14.0,
        "orphan-session",
        "orphan-intent",
        "",
        "",
        payload,
    )
    orphan = AIDecisionEvent(
        2,
        committed.event_hash,
        orphan_hash,
        "orphan",
        14.0,
        "orphan-session",
        "orphan-intent",
        "",
        "",
        payload,
    )
    backend.put_if_absent(
        "journal",
        f"event:{orphan_hash}",
        orphan,
    )
    assert journal.verify_root(orphan_hash)
    assert not journal.root_is_ancestor(
        orphan_hash
    )


def test_historical_root_corruption_is_detected():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 15.0,
    )
    first = append_one(journal, kind="first")
    append_one(journal, kind="second")
    key = journal._event_key(
        first.event_hash
    )
    record = backend.get(
        "journal",
        key,
    )
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            first,
            summary="tampered historical",
        ),
    )
    assert not journal.verify_root(
        first.event_hash
    )
    assert not journal.root_is_ancestor(
        first.event_hash
    )


def test_snapshot_at_rejects_malformed_root():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="SHA-256"):
        journal.snapshot_at("bad")


def test_historical_root_stays_valid_after_many_later_events():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 16.0,
    )
    first = append_one(journal, kind="first")
    for index in range(20):
        append_one(
            journal,
            kind=f"later-{index}",
            session_id=f"session-{index}",
        )
    assert journal.verify_root(
        first.event_hash
    )
    assert journal.root_is_ancestor(
        first.event_hash
    )
    assert journal.snapshot_at(
        first.event_hash
    ) == (first,)
