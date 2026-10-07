import pytest
from skeleton.runtime.model_eviction import *


def test_pinned_and_inflight_models_never_evict():
    for state in (DrainState(0, True), DrainState(1, False)):
        with pytest.raises(PermissionError):
            evict("m", state, EvictionPolicy(10), 20)


def test_eviction_is_reloadable_and_thrash_guarded():
    assert evict("m", DrainState(0, False), EvictionPolicy(10), 20).reloadable
    with pytest.raises(PermissionError):
        evict("m", DrainState(0, False), EvictionPolicy(10), 1)


def test_negative_inflight_and_idle_rejected():
    with pytest.raises(ValueError):
        DrainState(-1, False)
    with pytest.raises(ValueError):
        evict("m", DrainState(0, False), EvictionPolicy(1), -1)


def test_safe_boundary_and_nonreloadable_policy_are_explicit():
    state = DrainState(0, False)
    assert state.safe
    decision = evict(
        "m",
        state,
        EvictionPolicy(0, allow_reload=False),
        0,
        reason="capacity-pressure",
    )
    assert decision.reason == "capacity-pressure"
    assert not decision.reloadable


def test_invalid_policy_and_reason_fail_closed():
    with pytest.raises(ValueError):
        EvictionPolicy(True)
    with pytest.raises(ValueError):
        evict("m", DrainState(0, False), EvictionPolicy(0), 0, reason="")
