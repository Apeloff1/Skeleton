"""Acceptance checks for academy_tutorial."""
import pytest
from skeleton.forge.dialogue_sessions_v1.academy_tutorial import State, BEATS, RAPPORT_GATE, advance, replay, snapshot

def cmd(i="a", choice="introduce", version=0, evidence=""):
    return {"id": i, "choice": choice, "version": version, "evidence": evidence}

def test_initial_status():
    assert snapshot(State())["scene"] == "academy_tutorial"
    assert snapshot(State())["next"] == "introduce"

def test_accept_opening():
    updated, receipt = advance(State(), cmd())
    assert receipt.accepted and updated.beat == 1 and updated.version == 1

def test_order_gate():
    state = State()
    unchanged, receipt = advance(state, cmd(choice="leave"))
    assert unchanged is state and receipt.reason == "out-of-order"

def test_evidence_gate():
    state, _ = replay([cmd(), cmd("b", "listen", 1)])
    unchanged, receipt = advance(state, cmd("c", "reveal", 2))
    assert unchanged is state and receipt.reason == "proof-required"

def test_evidence_reuse_rejected():
    state, _ = replay([cmd(), cmd("b", "listen", 1), cmd("c", "reveal", 2, "proof")])
    unchanged, receipt = advance(state, cmd("d", "propose", 3, "proof"))
    assert unchanged is state and receipt.reason == "proof-used"

def test_rapport_gate():
    state = State(beat=3, rapport=RAPPORT_GATE-1)
    unchanged, receipt = advance(state, cmd("d", "propose", 0, "proof"))
    assert unchanged is state and receipt.reason == "rapport-low"

def test_duplicate_event():
    state, _ = advance(State(), cmd())
    unchanged, receipt = advance(state, cmd("a", "listen", 1))
    assert unchanged is state and receipt.reason == "duplicate"

def test_stale_version():
    state, _ = advance(State(), cmd())
    unchanged, receipt = advance(state, cmd("b", "listen", 0))
    assert unchanged is state and receipt.reason == "stale"

def test_terminal_withdrawal():
    state, receipt = advance(State(), cmd(choice="withdraw"))
    assert receipt.accepted and state.status == "withdrawn"
    unchanged, rejected = advance(state, cmd("b", version=1))
    assert unchanged is state and rejected.reason == "terminal"

def test_replay_deterministic():
    commands = [cmd(), cmd("b", "listen", 1)]
    assert replay(commands) == replay(commands)

@pytest.mark.parametrize("bad", [None, True, -1, 1.5])
def test_invalid_version(bad):
    with pytest.raises(ValueError):
        advance(State(), cmd(version=bad))

@pytest.mark.parametrize("bad", ["", None, "admin", "skip"])
def test_invalid_choice(bad):
    with pytest.raises(ValueError):
        advance(State(), cmd(choice=bad))

def test_extra_fields():
    with pytest.raises(ValueError):
        advance(State(), {**cmd(), "force": True})

def test_invalid_state():
    with pytest.raises(ValueError):
        State(tension=101)
    with pytest.raises(ValueError):
        State(beat=len(BEATS), status="active")
