"""Deterministic acceptance contracts for mystery_discovery."""
import pytest
from skeleton.forge.dialogue_sessions_v1.mystery_discovery import State, BEATS, apply, replay, snapshot, MIN_RAPPORT

def command(i="a", choice="opening", v=0, proof=""):
    return {"id": i, "choice": choice, "version": v, "proof": proof}

def test_metadata():
    assert snapshot(State())["scene"] == "mystery_discovery"
    assert snapshot(State())["next"] == "opening"

def test_advance():
    state, receipt = apply(State(), command())
    assert receipt.accepted and state.beat == 1 and state.version == 1

def test_out_of_order():
    state = State()
    next_state, receipt = apply(state, command(choice="departure"))
    assert next_state is state and receipt.reason == "out-of-order"

def test_proof_gate():
    state, _ = replay([command(), command("b", "question", 1)])
    unchanged, receipt = apply(state, command("c", "disclosure", 2))
    assert unchanged is state and receipt.reason == "proof-required"

def test_duplicate():
    state, _ = apply(State(), command())
    unchanged, receipt = apply(state, command("a", "question", 1))
    assert unchanged is state and receipt.reason == "duplicate"

def test_stale():
    state, _ = apply(State(), command())
    unchanged, receipt = apply(state, command("b", "question", 0))
    assert unchanged is state and receipt.reason == "stale"

def test_proof_reuse():
    state, _ = replay([command(), command("b", "question", 1), command("c", "disclosure", 2, "proof")])
    unchanged, receipt = apply(state, command("d", "offer", 3, "proof"))
    assert unchanged is state and receipt.reason == "proof-reused"

def test_rapport_gate():
    state = State(beat=3, rapport=MIN_RAPPORT-1)
    unchanged, receipt = apply(state, command("offer", "offer", 0, "distinct-proof"))
    assert unchanged is state and receipt.reason == "rapport"

def test_withdraw_terminal():
    state, receipt = apply(State(), command(choice="withdraw"))
    assert receipt.accepted and state.status == "withdrawn"
    unchanged, second = apply(state, command("b", "opening", 1))
    assert unchanged is state and second.reason == "terminal"

def test_deterministic_replay():
    actions = [command(), command("b", "question", 1)]
    assert replay(actions) == replay(actions)

@pytest.mark.parametrize("invalid", [None, True, 1.5, -1])
def test_invalid_version(invalid):
    with pytest.raises(ValueError):
        apply(State(), command(v=invalid))

@pytest.mark.parametrize("invalid", [None, "", "skip", "admin"])
def test_invalid_choice(invalid):
    with pytest.raises(ValueError):
        apply(State(), command(choice=invalid))

def test_unexpected_fields():
    with pytest.raises(ValueError):
        apply(State(), {**command(), "override": True})

def test_bad_state():
    with pytest.raises(ValueError):
        State(rapport=True)
    with pytest.raises(ValueError):
        State(beat=len(BEATS), status="active")
