"""Executable regression contracts for fear state transitions."""
import pytest
from skeleton.forge.game_mechanics_v2.fear import (
    State, MAX_VALUE, INITIAL_VALUE, LOW_WATERMARK, apply, assess, replay,
)

def event(identity="evt-1", action="gain", amount=2, tick=1):
    return {"id": identity, "action": action, "amount": amount, "tick": tick}

def test_initial_state_and_capacity():
    state = State()
    report = assess(state)
    assert report["value"] == INITIAL_VALUE
    assert report["capacity"] == MAX_VALUE
    assert report["remaining"] == MAX_VALUE - INITIAL_VALUE

def test_gain_is_bounded():
    state, receipt = apply(State(), event(amount=MAX_VALUE))
    assert receipt.accepted
    assert state.value == MAX_VALUE
    assert receipt.before == INITIAL_VALUE

def test_spend_never_goes_negative():
    state, receipt = apply(State(), event(action="spend", amount=MAX_VALUE))
    assert receipt.accepted
    assert state.value == 0
    assert assess(state)["low"]

def test_duplicate_is_idempotent():
    state, first = apply(State(), event())
    duplicate_state, second = apply(state, event(tick=2))
    assert first.accepted
    assert not second.accepted
    assert second.reason == "duplicate"
    assert duplicate_state is state

def test_nonmonotonic_tick_fails_closed():
    state, _ = apply(State(), event())
    unchanged, receipt = apply(state, event("other", tick=1))
    assert unchanged is state
    assert receipt.reason == "nonmonotonic-tick"

@pytest.mark.parametrize("bad", [-1, 1.5, True, None, MAX_VALUE + 1])
def test_invalid_amount_rejected(bad):
    with pytest.raises(ValueError):
        apply(State(), event(amount=bad))

@pytest.mark.parametrize("action", ["remove", "", None, "grant-admin"])
def test_unknown_action_rejected(action):
    with pytest.raises(ValueError):
        apply(State(), event(action=action))

def test_replay_is_deterministic():
    commands = [event("a", "gain", 3, 1), event("b", "spend", 2, 2)]
    assert replay(commands) == replay(commands)
    assert len(replay(commands)[1]) == 2

def test_recover_and_decay_branches():
    state, _ = apply(State(), event("recover", "recover", 4, 1))
    next_state, receipt = apply(state, event("decay", "decay", 1, 2))
    assert receipt.accepted
    assert 0 <= next_state.value <= MAX_VALUE

def test_unexpected_fields_rejected():
    with pytest.raises(ValueError):
        apply(State(), {**event(), "role": "admin"})

def test_state_invariants():
    with pytest.raises(ValueError):
        State(value=MAX_VALUE + 1)
    with pytest.raises(ValueError):
        State(tick=-1)
    assert assess(State(value=LOW_WATERMARK))["low"]
