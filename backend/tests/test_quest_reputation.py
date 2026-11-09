import pytest

from core.quest_graph import Objective, QuestDefinition, QuestGraph
from core.reputation import FactionDefinition, ReputationState


def test_quest_prerequisites_progress_and_unlocks():
    graph = QuestGraph((
        QuestDefinition(
            "q1", "First", (Objective("collect", target=2, filters=(("item", "wood"),)),),
            rewards=(("xp", 10),),
        ),
        QuestDefinition(
            "q2", "Second", (Objective("visit", target=1, filters=(("location", "port"),)),),
            prerequisite="q1",
        ),
    ))
    assert [q.id for q in graph.available()] == ["q1"]
    graph.activate("q1")
    assert graph.ingest("collect", {"item": "stone"}) == ()
    assert graph.progress("q1").counts == [0]
    graph.ingest("collect", {"item": "wood"})
    result = graph.ingest("collect", {"item": "wood"})
    assert result[0].quest_id == "q1"
    assert result[0].rewards == {"xp": 10}
    assert result[0].newly_available == ("q2",)
    assert graph.completed_ids() == ("q1",)


def test_quest_rejects_missing_prerequisite_and_invalid_amount():
    graph = QuestGraph((
        QuestDefinition("a", "A", (Objective("x"),)),
        QuestDefinition("b", "B", (Objective("y"),), prerequisite="a"),
    ))
    with pytest.raises(ValueError, match="prerequisite"):
        graph.activate("b")
    graph.activate("a")
    with pytest.raises(ValueError, match="positive"):
        graph.ingest("x", amount=0)


def test_reputation_spills_to_allies_and_enemies():
    state = ReputationState({
        "guild": FactionDefinition("guild", allies=("merchants",), enemies=("pirates",)),
        "merchants": FactionDefinition("merchants"),
        "pirates": FactionDefinition("pirates"),
    })
    changes = state.adjust("guild", 1000)
    assert changes == {"guild": 1000, "merchants": 200, "pirates": -250}
    assert state.band("guild").name == "friendly"
    assert state.band("pirates").name == "hostile"


def test_reputation_benefits_accumulate_by_band():
    state = ReputationState({
        "guild": FactionDefinition(
            "guild",
            benefits=(
                ("friendly", ("shop",)),
                ("honored", ("quests",)),
                ("revered", ("boat",)),
            ),
        )
    })
    state.adjust("guild", 3500, ally_ratio=0, enemy_ratio=0)
    assert state.band("guild").name == "honored"
    assert state.benefits("guild") == ("shop", "quests")


def test_reputation_clamps_and_unknown_factions_fail_closed():
    state = ReputationState({"guild": FactionDefinition("guild")})
    state.adjust("guild", -100000)
    assert state.values["guild"] == -1000
    with pytest.raises(KeyError):
        state.adjust("missing", 10)
