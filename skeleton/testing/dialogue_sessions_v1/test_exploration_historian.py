"""Regression tests for exploration_historian."""
import pytest
from skeleton.forge.dialogue_sessions_v1.exploration_historian import State, STAGES, choose, replay, snapshot, MIN_TRUST

def cmd(i="e1", choice="greet", version=0, evidence=""):
    return {"id": i, "choice": choice, "expected_version": version, "evidence": evidence}

def test_initial_snapshot():
    assert snapshot(State())["scene"] == "exploration_historian"
    assert snapshot(State())["choice"] == "greet"

def test_first_beat_advances():
    state, receipt = choose(State(), cmd())
    assert receipt.accepted and state.stage == 1 and state.version == 1

def test_wrong_order_rejected():
    old = State()
    state, receipt = choose(old, cmd(choice="close"))
    assert state is old and receipt.reason == "stage-order"

def test_proof_required():
    state, _ = replay([cmd(), cmd("e2", "ask", 1)])
    unchanged, receipt = choose(state, cmd("e3", "explain", 2))
    assert unchanged is state and receipt.reason == "proof-required"

def test_duplicate_rejected():
    state, _ = choose(State(), cmd())
    unchanged, receipt = choose(state, cmd("e1", "ask", 1))
    assert unchanged is state and receipt.reason == "replay"

def test_stale_version_rejected():
    state, _ = choose(State(), cmd())
    unchanged, receipt = choose(state, cmd("e2", "ask", 0))
    assert unchanged is state and receipt.reason == "stale"

def test_withdraw_terminal():
    state, receipt = choose(State(), cmd(choice="withdraw"))
    assert receipt.accepted and state.status == "withdrawn"
    unchanged, rejected = choose(state, cmd("e2", "greet", 1))
    assert unchanged is state and rejected.reason == "terminal"

def test_evidence_replay_rejected():
    state, _ = replay([cmd(), cmd("e2", "ask", 1), cmd("e3", "explain", 2, "proof")])
    unchanged, receipt = choose(state, cmd("e4", "negotiate", 3, "proof"))
    assert unchanged is state and receipt.reason == "proof-replayed"

def test_insufficient_rapport():
    state = State(stage=3, trust=MIN_TRUST-1)
    unchanged, receipt = choose(state, cmd("e4", "negotiate", 0, "proof"))
    assert unchanged is state and receipt.reason == "rapport-gate"

@pytest.mark.parametrize("version", [-1, None, True, 1.5])
def test_bad_version(version):
    with pytest.raises(ValueError):
        choose(State(), cmd(version=version))

@pytest.mark.parametrize("choice", [None, "", "admin", "skip"])
def test_bad_choice(choice):
    with pytest.raises(ValueError):
        choose(State(), cmd(choice=choice))

def test_extra_fields():
    with pytest.raises(ValueError):
        choose(State(), {**cmd(), "override": True})

def test_state_validation():
    with pytest.raises(ValueError):
        State(trust=101)
    with pytest.raises(ValueError):
        State(stage=len(STAGES), status="active")

def test_replay_deterministic():
    commands = [cmd(), cmd("e2", "ask", 1)]
    assert replay(commands) == replay(commands)
