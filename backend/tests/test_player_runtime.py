from core.player_runtime import PlayerRuntime
from core.progression import Medal, ProgressionState
from core.quest_graph import Objective, QuestDefinition, QuestGraph
from core.reputation import FactionDefinition, ReputationState


def build_runtime():
    quests = QuestGraph((
        QuestDefinition(
            "finish_rim",
            "Finish Rim",
            (Objective("complete_stage", filters=(("stage_id", "rim"),)),),
            rewards=(("xp", 100), ("gold", 50), ("item", "wing_pin"), ("reputation", {"guild": 600})),
        ),
    ))
    quests.activate("finish_rim")
    return PlayerRuntime(
        ProgressionState(unlocked={"rim"}),
        quests,
        ReputationState({"guild": FactionDefinition("guild")}),
    )


def test_finish_updates_progression_and_quest_rewards():
    runtime = build_runtime()
    result = runtime.record_finish(
        "rim",
        score=41.2,
        medal=Medal.GOLD,
        ghost=[{"t": 0.0}],
        distance=1000,
        unlocks={"rim": ("bowl",)},
    )
    assert result["progression"].improved is True
    assert runtime.xp == 100
    assert runtime.gold == 50
    assert runtime.inventory == {"wing_pin": 1}
    assert runtime.reputation.values["guild"] == 600
    assert "bowl" in runtime.progression.unlocked
    assert runtime.quests.completed_ids() == ("finish_rim",)


def test_snapshot_is_product_ready():
    runtime = build_runtime()
    snap = runtime.snapshot()
    assert snap["xp"] == 0
    assert snap["progression"]["unlocked"] == ["rim"]
    assert snap["reputation"] == {"guild": 0}
