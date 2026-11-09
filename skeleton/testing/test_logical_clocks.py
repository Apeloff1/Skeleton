from __future__ import annotations

import pytest

from skeleton.foundation.logical_clock import (
    CausalRelation,
    FencingToken,
    LogicalClock,
    SequenceNumber,
    VectorClock,
)


def test_lamport_tick_and_observe_are_monotonic() -> None:
    a = LogicalClock("worker_a").tick().tick()
    b = LogicalClock("worker_b").tick()
    observed = b.observe(a)
    assert observed.node_id == "worker_b"
    assert observed.counter == SequenceNumber(3)


def test_vector_clock_detects_concurrency_without_timestamps() -> None:
    left = VectorClock.from_mapping({"a": 2, "b": 1})
    right = VectorClock.from_mapping({"a": 1, "b": 2})
    assert left.relation(right) is CausalRelation.CONCURRENT
    assert right.relation(left) is CausalRelation.CONCURRENT


def test_vector_clock_orders_causal_history() -> None:
    before = VectorClock.from_mapping({"a": 1})
    after = VectorClock.from_mapping({"a": 2, "b": 1})
    assert before.relation(after) is CausalRelation.BEFORE
    assert after.relation(before) is CausalRelation.AFTER
    assert after.relation(after) is CausalRelation.EQUAL


def test_merge_is_commutative_and_preserves_maxima() -> None:
    a = VectorClock.from_mapping({"a": 4, "b": 1})
    b = VectorClock.from_mapping({"a": 2, "b": 3, "c": 1})
    assert a.merge(b) == b.merge(a)
    assert a.merge(b).as_mapping() == {"a": 4, "b": 3, "c": 1}


def test_fencing_requires_strictly_newer_sequence() -> None:
    old = FencingToken(SequenceNumber(7))
    same = FencingToken(SequenceNumber(7))
    new = FencingToken(SequenceNumber(8))
    assert not same.supersedes(old)
    assert new.supersedes(old)


@pytest.mark.parametrize("value", [-1, True, 1 << 63])
def test_invalid_sequences_fail_closed(value) -> None:
    with pytest.raises(ValueError):
        SequenceNumber(value)


@pytest.mark.parametrize("node", ["", "Worker", "worker.a", "wørker", "worker a"])
def test_noncanonical_node_ids_fail_closed(node: str) -> None:
    with pytest.raises(ValueError):
        LogicalClock(node)


def test_counter_exhaustion_fails_closed() -> None:
    maximum = SequenceNumber((1 << 63) - 1)
    with pytest.raises(OverflowError):
        maximum.next()
    with pytest.raises(OverflowError):
        LogicalClock("a", maximum).observe(LogicalClock("b"))


def test_vector_clock_rejects_noncanonical_or_invalid_entries() -> None:
    with pytest.raises(ValueError):
        VectorClock.from_mapping({"Node": 1})
    with pytest.raises(ValueError):
        VectorClock.from_mapping({"node": -1})
