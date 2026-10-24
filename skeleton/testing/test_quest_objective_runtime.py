"""#807 B028: quest/objective runtime."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.quest_objective_runtime import (
    ObjectiveState, QuestDefinition, QuestError, QuestRuntime, run_quest,
)

QUEST = {
    "id": "q.bandits",
    "objectives": [
        {"id": "find_camp", "rewards": [{"kind": "xp", "amount": 10}]},
        {"id": "kill_bandits", "requires": ["find_camp"], "target": 3, "fail_on": ["camp_burned"],
         "rewards": [{"kind": "gold", "amount": 50}]},
        {"id": "loot_chest", "requires": ["find_camp"], "optional": True},
    ],
}


def _def() -> QuestDefinition:
    return QuestDefinition.from_mapping(QUEST)


def test_dependencies_gate_activation() -> None:
    rt = QuestRuntime(_def())
    assert rt.states["find_camp"] is ObjectiveState.ACTIVE
    assert rt.states["kill_bandits"] is ObjectiveState.LOCKED
    with pytest.raises(QuestError):
        rt.advance("kill_bandits")
    rt.advance("find_camp")
    assert rt.states["kill_bandits"] is ObjectiveState.ACTIVE


def test_completion_and_rewards() -> None:
    out = run_quest(QUEST, [{"advance": "find_camp"}, {"advance": "kill_bandits", "amount": 3}])
    assert out["status"] == "completed"
    assert out["rewards"] == [{"kind": "xp", "amount": 10}, {"kind": "gold", "amount": 50}]


def test_failure_state() -> None:
    out = run_quest(QUEST, [{"advance": "find_camp"}, {"signal": "camp_burned"}])
    assert out["status"] == "failed"


@pytest.mark.parametrize("bad", [
    {"id": "q", "objectives": []},
    {"id": "q", "objectives": [{"id": "a", "requires": ["b"]}, {"id": "b", "requires": ["a"]}]},
    {"id": "q", "objectives": [{"id": "a", "requires": ["ghost"]}]},
    {"id": "q", "objectives": [{"id": "a"}, {"id": "a"}]},
    {"id": "q", "objectives": [{"id": "a", "target": 0}]},
    {"id": "q", "objectives": [{"id": "a", "optional": True}]},
])
def test_invalid_definitions_fail_closed(bad: dict) -> None:
    with pytest.raises(QuestError):
        QuestDefinition.from_mapping(bad)


def test_snapshot_roundtrip_is_deterministic() -> None:
    rt = QuestRuntime(_def())
    rt.advance("find_camp")
    rt.advance("kill_bandits", 2)
    snap = rt.snapshot()
    restored = QuestRuntime.restore(_def(), snap)
    assert restored.snapshot() == snap
    assert restored.progress["kill_bandits"] == 2


def test_tampered_snapshot_rejected() -> None:
    rt = QuestRuntime(_def())
    rt.advance("find_camp")
    snap = rt.snapshot()
    snap["progress"]["kill_bandits"] = 3
    with pytest.raises(QuestError):
        QuestRuntime.restore(_def(), snap)


def test_snapshot_for_other_definition_rejected() -> None:
    snap = QuestRuntime(_def()).snapshot()
    other = QuestDefinition.from_mapping({"id": "q2", "objectives": [{"id": "x"}]})
    with pytest.raises(QuestError):
        QuestRuntime.restore(other, snap)
