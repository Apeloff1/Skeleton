"""Adversarial qualification for recovered deterministic assurance."""
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat

import pytest

from skeleton.frontier.assurance import (
    BoundedInt, Decision, InvariantViolation, MonotonicCounter, QualityGate,
    Snapshot, Verification, require, state_digest,
)


@pytest.mark.parametrize("check", [1, "true", [], None])
def test_truthiness_cannot_authorize(check):
    with pytest.raises(ValueError):
        QualityGate.from_checks([check])
    with pytest.raises(InvariantViolation):
        require(check, "explicit true required")


def test_empty_and_unbounded_gate_inventories():
    assert not QualityGate.from_checks([]).passed
    with pytest.raises(ValueError):
        QualityGate.from_checks(repeat(True))
    with pytest.raises(ValueError):
        Verification("artifact", True, ())
    with pytest.raises(ValueError):
        Verification("artifact", True, ("unit", "unit"))


def test_snapshot_is_deeply_immutable_and_digest_checked():
    state = {"a": [{"b": 1}]}
    snapshot = Snapshot.capture(0, state)
    state["a"][0]["b"] = 2
    assert snapshot.state["a"][0]["b"] == 1
    with pytest.raises(TypeError):
        snapshot.state["a"][0]["b"] = 3
    assert state_digest(snapshot.state) == snapshot.digest
    with pytest.raises(ValueError):
        Snapshot(0, {"a": 2}, snapshot.digest)
    with pytest.raises(ValueError):
        Snapshot.capture(True, {})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), {1: "x"}, b"bytes"])
def test_unsupported_state_has_no_digest(value):
    with pytest.raises(ValueError):
        state_digest(value)


def test_cycle_and_excessive_depth_rejected():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError):
        state_digest(cycle)
    with pytest.raises(ValueError):
        state_digest("x" * 1_048_577)


def test_decision_evidence_cannot_be_changed_after_admission():
    evidence = {"unit": "success"}
    decision = Decision("admit", True, "validated", evidence)
    evidence["unit"] = "failure"
    assert decision.evidence["unit"] == "success"
    with pytest.raises(TypeError):
        decision.evidence["unit"] = "failure"
    with pytest.raises(ValueError):
        Decision("admit", 1, "invalid")
    with pytest.raises(ValueError):
        Verification("artifact", 1, ("unit",))


def test_counter_serializes_and_bounds_reject_booleans():
    counter = MonotonicCounter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: counter.next(), range(512)))
    assert sorted(results) == list(range(1, 513))
    assert counter.value == 512
    with pytest.raises(ValueError):
        MonotonicCounter(True)
    with pytest.raises(ValueError):
        BoundedInt(True, 0, 2)
    with pytest.raises(ValueError):
        BoundedInt(1, 0, 2).clamp(1.5)
