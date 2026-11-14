"""Same-named questflow acceptance module with a distinct source package.

The sibling dialogue_sessions_v1/test_companions_rescue.py covers dialogue.
These independent checks cover quest-state execution, not a duplicate import.
"""
from __future__ import annotations

import pytest

from skeleton.forge.questflows_v1.companions_rescue import (
    QuestState, STAGES, decide, inspect, replay,
)


def _step(identifier="quest0", *, version=0, evidence=()):
    return {
        "id": identifier,
        "action": "advance",
        "expected_version": version,
        "evidence": list(evidence),
    }


def test_quest_proof_gate_is_independent_of_dialogue_rapport():
    initial = QuestState()
    view = inspect(initial)
    assert view["required_evidence"] == STAGES[0][1]
    unchanged, denied = decide(initial, _step())
    assert unchanged is initial
    assert not denied.accepted
    assert denied.reason == "required-evidence-missing"


def test_quest_rescue_commits_one_causal_stage_per_proof():
    state = QuestState()
    for index, stage in enumerate(STAGES):
        updated, receipt = decide(
            state,
            _step(f"quest{index}", version=index, evidence=(stage[1],)),
        )
        assert receipt.accepted
        assert updated.version == index + 1
        assert stage[2] in updated.grants
        state = updated
    assert state.status == "completed"
    assert state.stage == len(STAGES)


def test_replay_is_deterministic_and_does_not_reissue_external_effects():
    commands = [_step(f"q{i}", version=i, evidence=(stage[1],))
                for i, stage in enumerate(STAGES)]
    first = replay(commands)
    assert first == replay(commands)
    assert all(receipt.accepted for receipt in first[1])


def test_duplicate_and_stale_quest_events_are_denied():
    advanced, _ = decide(
        QuestState(), _step("q0", evidence=(STAGES[0][1],))
    )
    same, duplicate = decide(
        advanced, _step("q0", version=1, evidence=(STAGES[1][1],))
    )
    assert same is advanced and duplicate.reason == "duplicate-event"
    same, stale = decide(
        advanced, _step("q1", version=0, evidence=(STAGES[1][1],))
    )
    assert same is advanced and stale.reason == "stale-version"


@pytest.mark.parametrize("invalid", [None, True, -1, 1.5, "0"])
def test_quest_versions_do_not_coerce(invalid):
    with pytest.raises(ValueError):
        decide(QuestState(), _step(version=invalid))


def test_quest_abandon_cannot_be_reopened():
    terminal, receipt = decide(QuestState(), {
        "id": "quit",
        "action": "abandon",
        "expected_version": 0,
        "evidence": [],
    })
    assert receipt.accepted and terminal.status == "abandoned"
    same, denied = decide(
        terminal, _step("restart", version=1, evidence=(STAGES[0][1],))
    )
    assert same is terminal and denied.reason == "terminal-state"
