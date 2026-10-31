"""Faction governance regressions: trade_merchant_seats."""
import pytest
from skeleton.forge.faction_governance_v1.trade_merchant_seats import (
    State, DELEGATES, QUORUM, APPROVAL, MAX_RECEIPTS,
    decide, snapshot, replay,
)

PROPOSAL = "fictional-policy-change"

def cmd(key="open", action="open", version=0, delegate="", choice="", proposal=PROPOSAL):
    return {
        "id": key, "action": action, "proposal": proposal,
        "delegate": delegate, "choice": choice, "expected_version": version,
    }

def open_ballot():
    return decide(State(), cmd())[0]

def voted_yes():
    state = open_ballot()
    for i in range(QUORUM):
        state, decision = decide(
            state, cmd(f"vote-{i}", "cast", i+1, DELEGATES[i], "yes")
        )
        assert decision.accepted
    return state

def test_initial_inventory():
    view = snapshot(State())
    assert view["policy_id"] == "trade_merchant_seats"
    assert view["phase"] == "idle"
    assert view["quorum"] == QUORUM

def test_open_ballot():
    state, receipt = decide(State(), cmd())
    assert receipt.accepted and receipt.reason == "opened"
    assert state.phase == "voting" and state.version == 1

def test_approval_with_quorum():
    state = voted_yes()
    approved, receipt = decide(state, cmd("final", "finalize", state.version))
    assert receipt.accepted and receipt.reason == "approved"
    assert approved.phase == "approved"
    assert snapshot(approved)["yes"] == QUORUM

def test_quorum_failure():
    initial = open_ballot()
    unchanged, receipt = decide(initial, cmd("final", "finalize", 1))
    assert unchanged is initial and receipt.reason == "quorum-not-met"

def test_one_ballot_per_delegate():
    state = open_ballot()
    state, _ = decide(state, cmd("a", "cast", 1, DELEGATES[0], "yes"))
    unchanged, receipt = decide(state, cmd("b", "cast", 2, DELEGATES[0], "no"))
    assert unchanged is state
    assert receipt.reason == "delegate-already-voted"

def test_duplicate_event_identity():
    state = open_ballot()
    unchanged, receipt = decide(state, cmd("open", "cast", 1, DELEGATES[0], "yes"))
    assert unchanged is state and receipt.reason == "duplicate-event"

def test_stale_version():
    state = open_ballot()
    unchanged, receipt = decide(state, cmd("a", "cast", 0, DELEGATES[0], "yes"))
    assert unchanged is state and receipt.reason == "stale-version"

def test_proposal_binding():
    state = open_ballot()
    unchanged, receipt = decide(state, cmd("a", "cast", 1, DELEGATES[0], "yes", "other"))
    assert unchanged is state and receipt.reason == "proposal-mismatch"

def test_cancel_terminal():
    state = open_ballot()
    cancelled, receipt = decide(state, cmd("cancel", "cancel", 1))
    assert receipt.accepted and cancelled.phase == "rejected"
    unchanged, next_receipt = decide(cancelled, cmd("a", "cast", 2, DELEGATES[0], "yes"))
    assert unchanged is cancelled and next_receipt.reason == "not-voting"

def test_inspection_has_no_side_effect():
    state = State()
    unchanged, receipt = decide(state, cmd("inspect", "inspect"))
    assert unchanged is state and receipt.reason == "read-only"

def test_reject_majority_no():
    state = open_ballot()
    for i in range(QUORUM):
        state, _ = decide(state, cmd(f"no-{i}", "cast", i+1, DELEGATES[i], "no"))
    rejected, receipt = decide(state, cmd("final", "finalize", state.version))
    assert receipt.reason == "rejected" and rejected.phase == "rejected"

@pytest.mark.parametrize("version", [None, True, -1, 1.5])
def test_invalid_version(version):
    with pytest.raises(ValueError):
        decide(State(), cmd(version=version))

@pytest.mark.parametrize("choice", [None, True, "override", "abstain"])
def test_invalid_choice(choice):
    with pytest.raises(ValueError):
        decide(State(), cmd(choice=choice))

def test_unknown_fields():
    with pytest.raises(ValueError):
        decide(State(), {**cmd(), "override": True})

def test_immutable_state_invariants():
    with pytest.raises(ValueError):
        State(phase="approved", proposal="")
    with pytest.raises(ValueError):
        State(version=True)
    with pytest.raises(ValueError):
        State(ballots=(("delegate_1", "yes"), ("delegate_1", "no")))
    with pytest.raises(ValueError):
        State(event_ids=frozenset({""}))

def test_deterministic_replay():
    sequence = [cmd()] + [
        cmd(f"vote-{i}", "cast", i+1, DELEGATES[i], "yes")
        for i in range(QUORUM)
    ] + [cmd("final", "finalize", QUORUM+1)]
    assert replay(sequence) == replay(sequence)
    assert replay(sequence)[0].phase == "approved"

def test_bounded_replay():
    with pytest.raises(ValueError):
        replay([cmd()] * (MAX_RECEIPTS + 1))
