"""Durable AI decision journal restart and corruption tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.journal import AIDecisionJournal


def test_distributed_journal_empty():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
    )
    assert journal.snapshot() == ()
    assert journal.root_hash() == AIDecisionJournal.GENESIS
    assert journal.verify()


def test_distributed_journal_append():
    now = [100.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
        clock=lambda: now[0],
    )
    event = journal.append(
        "ai.plan.proposed",
        session_id="s",
        intent_id="i",
        proposal_id="p",
        summary="proposed",
        data={"model_id": "m"},
    )
    assert event.sequence == 1
    assert event.previous_hash == AIDecisionJournal.GENESIS
    assert event.observed_at == 100
    assert event.data["model_id"] == "m"
    assert journal.verify()


def test_distributed_journal_restart_preserves_history():
    store = InMemoryFencedStore()
    first = DistributedAIDecisionJournal(
        store,
        namespace="journal",
        clock=lambda: 1.0,
    )
    one = first.append(
        "one",
        session_id="s",
        intent_id="i",
    )
    second = DistributedAIDecisionJournal(
        store,
        namespace="journal",
        clock=lambda: 2.0,
    )
    two = second.append(
        "two",
        session_id="s",
        intent_id="i",
    )
    events = second.snapshot()
    assert [item.kind for item in events] == ["one", "two"]
    assert two.previous_hash == one.event_hash
    assert second.verify()


def test_distributed_journal_hashes_match_local_algorithm():
    store = InMemoryFencedStore()
    distributed = DistributedAIDecisionJournal(
        store,
        namespace="journal",
        clock=lambda: 1.5,
    )
    local = AIDecisionJournal(clock=lambda: 1.5)
    d = distributed.append(
        "kind",
        session_id="s",
        intent_id="i",
        proposal_id="p",
        summary="summary",
        data={"x": 1},
    )
    l = local.append(
        "kind",
        session_id="s",
        intent_id="i",
        proposal_id="p",
        summary="summary",
        data={"x": 1},
    )
    assert d.event_hash == l.event_hash


def test_distributed_journal_multiple_hashes_match_local():
    times = iter([1.0, 2.0, 3.0])
    local_times = iter([1.0, 2.0, 3.0])
    distributed = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
        clock=lambda: next(times),
    )
    local = AIDecisionJournal(clock=lambda: next(local_times))
    for index in range(3):
        kwargs = dict(
            kind=f"k{index}",
            session_id="s",
            intent_id="i",
            proposal_id=f"p{index}",
            summary=f"summary {index}",
            data={"index": index},
        )
        distributed.append(**kwargs)
        local.append(**kwargs)
    assert [e.event_hash for e in distributed.snapshot()] == [
        e.event_hash for e in local.snapshot()
    ]


def test_distributed_journal_capacity():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
        max_events=1,
    )
    journal.append("one", session_id="s", intent_id="i")
    with pytest.raises(RuntimeError):
        journal.append("two", session_id="s", intent_id="i")


def test_distributed_journal_outer_chain_tamper():
    store = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(store, namespace="journal")
    journal.append("one", session_id="s", intent_id="i")
    node = journal._chain.snapshot()[0]
    record = store.get("journal", f"node:{node.node_hash}")
    store.compare_and_swap(
        "journal",
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload={"kind": "tampered"}),
    )
    assert not journal.verify()


def test_distributed_journal_summary_limit():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
    )
    with pytest.raises(ValueError, match="summary"):
        journal.append(
            "one",
            session_id="s",
            intent_id="i",
            summary="x" * 2049,
        )


def test_distributed_journal_data_field_limit():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
    )
    with pytest.raises(ValueError, match="data"):
        journal.append(
            "one",
            session_id="s",
            intent_id="i",
            data={str(i): i for i in range(129)},
        )


def test_distributed_journal_kind_validation():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="journal",
    )
    with pytest.raises(ValueError):
        journal.append("", session_id="s", intent_id="i")
