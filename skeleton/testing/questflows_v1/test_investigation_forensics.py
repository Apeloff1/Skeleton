"""Regression suite for the forensics workflow contract."""
from __future__ import annotations

import pytest

from skeleton.forge.questflows_v1.investigation_forensics import (
    QuestState, STAGES, MAX_EVENTS, decide, inspect, replay,
)


_UNSET = object()


def command(key="e0", action="advance", version=0, evidence=_UNSET):
    return {
        "id": key, "action": action, "expected_version": version,
        "evidence": [] if evidence is _UNSET else evidence,
    }


def test_metadata_has_pending_evidence():
    view = inspect(QuestState())
    assert view["stage_count"] == 4
    assert view["next_stage"] == STAGES[0][0]
    assert view["required_evidence"] == STAGES[0][1]


def test_missing_proof_rejected():
    state, decision = decide(QuestState(), command())
    assert state == QuestState()
    assert decision.reason == "required-evidence-missing"


def test_evidence_advances_one_stage():
    state, receipt = decide(
        QuestState(), command(evidence=[STAGES[0][1]])
    )
    assert receipt.accepted
    assert state.stage == 1
    assert STAGES[0][2] in state.grants
    assert state.version == 1


def test_full_story_completes_deterministically():
    steps = [
        command(f"e{i}", version=i, evidence=[stage[1]])
        for i, stage in enumerate(STAGES)
    ]
    state, receipts = replay(steps)
    assert state.status == "completed"
    assert state.stage == len(STAGES)
    assert len(state.grants) == len(STAGES)
    assert all(receipt.accepted for receipt in receipts)
    assert replay(steps) == (state, receipts)


def test_duplicate_event_rejected_before_version_change():
    state, _ = decide(QuestState(), command(evidence=[STAGES[0][1]]))
    unchanged, receipt = decide(
        state, command("e0", version=state.version, evidence=[STAGES[1][1]])
    )
    assert unchanged is state
    assert receipt.reason == "duplicate-event"


def test_version_fence_rejects_races():
    state, _ = decide(QuestState(), command(evidence=[STAGES[0][1]]))
    unchanged, receipt = decide(
        state, command("e1", version=0, evidence=[STAGES[1][1]])
    )
    assert unchanged is state
    assert receipt.reason == "stale-version"


def test_abandon_is_terminal():
    state, receipt = decide(QuestState(), command(action="abandon"))
    assert receipt.accepted
    assert state.status == "abandoned"
    unchanged, retry = decide(
        state, command("next", version=1, evidence=[STAGES[0][1]])
    )
    assert unchanged == state
    assert retry.reason == "terminal-state"


def test_inspect_command_never_mutates():
    state, receipt = decide(QuestState(), command(action="inspect"))
    assert state == QuestState()
    assert receipt.reason == "inspection-is-readonly"


@pytest.mark.parametrize("invalid", [
    None, True, -1, 1.5, "0",
])
def test_invalid_expected_version_rejected(invalid):
    with pytest.raises(ValueError):
        decide(QuestState(), command(version=invalid))


@pytest.mark.parametrize("invalid", [
    None, "proof", [None], [3], ["same", "same"], ["x" * 129],
])
def test_bad_evidence_rejected(invalid):
    with pytest.raises(ValueError):
        decide(QuestState(), command(evidence=invalid))


def test_unknown_action_and_extra_fields_rejected():
    with pytest.raises(ValueError):
        decide(QuestState(), command(action="override"))
    with pytest.raises(ValueError):
        decide(QuestState(), {**command(), "force": True})


def test_terminal_state_cannot_reopen():
    terminal, _ = replay([
        command(f"e{i}", version=i, evidence=[stage[1]])
        for i, stage in enumerate(STAGES)
    ])
    result, receipt = decide(
        terminal, command("reopen", version=4, evidence=[STAGES[0][1]])
    )
    assert result == terminal
    assert receipt.reason == "terminal-state"


def test_invalid_state_invariants():
    with pytest.raises(ValueError):
        QuestState(stage=-1)
    with pytest.raises(ValueError):
        QuestState(stage=4, status="active")
    with pytest.raises(ValueError):
        QuestState(stage=1, status="completed")
    with pytest.raises(ValueError):
        QuestState(version=-1)
    with pytest.raises(ValueError):
        QuestState(event_ids=frozenset({"a"}) | frozenset({""}))


def test_reconstructed_state_rejects_forged_completion():
    with pytest.raises(ValueError, match="grant-ledger-mismatch"):
        QuestState(stage=len(STAGES), version=len(STAGES), status="completed",
                   event_ids=frozenset(f"e{i}" for i in range(len(STAGES))))


def test_reconstructed_state_rejects_missing_event_ledger():
    with pytest.raises(ValueError, match="event-version-mismatch"):
        QuestState(version=1)


def test_completed_replay_state_reconstructs_consistently():
    steps = [command(f"e{i}", version=i, evidence=[stage[1]])
             for i, stage in enumerate(STAGES)]
    state, _ = replay(steps)
    assert QuestState(state.stage, state.version, state.status,
                      state.grants, state.event_ids) == state


def test_replay_batch_capacity_fails_closed():
    with pytest.raises(ValueError):
        replay([command()] * (MAX_EVENTS + 1))
