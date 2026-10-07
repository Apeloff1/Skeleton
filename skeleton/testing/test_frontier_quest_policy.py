from __future__ import annotations

import pytest

from skeleton.frontier.quests import (
    available_quests,
    initialize_progress,
    quest_from_record,
    reward_plan,
    select_quests_by_type,
    update_objective_progress,
)


def _quest(quest_id: str, **overrides):
    record = {
        "id": quest_id,
        "name": quest_id.replace("_", " ").title(),
        "type": "main_story",
        "chapter": 1,
        "description": "Source-shaped test quest.",
        "objectives": [{"type": "catch_fish", "count": 2}],
        "rewards": {"gold": 50, "xp": 100},
        "prerequisite": None,
        "giver": "barnacle_bill",
    }
    record.update(overrides)
    return quest_from_record(record)


def test_quest_adapter_preserves_domain_metadata_without_catalog_copy():
    quest = _quest("ms_001")

    assert quest.id == "ms_001"
    assert quest.quest_type == "main_story"
    assert quest.objectives[0]["count"] == 2
    assert quest.rewards == {"gold": 50, "xp": 100}
    assert quest.metadata["chapter"] == 1
    assert quest.metadata["giver"] == "barnacle_bill"


def test_available_quests_enforces_prerequisite_and_completion():
    first = _quest("ms_001")
    second = _quest("ms_002", prerequisite="ms_001")
    third = _quest("ms_003", prerequisite="ms_002")

    assert [quest.id for quest in available_quests([first, second, third], [])] == [
        "ms_001"
    ]
    assert [
        quest.id for quest in available_quests([first, second, third], ["ms_001"])
    ] == ["ms_002"]
    assert [
        quest.id
        for quest in available_quests(
            [first, second, third],
            ["ms_001", "ms_002"],
        )
    ] == ["ms_003"]


def test_available_quests_rejects_duplicate_catalog_ids():
    first = _quest("duplicate")
    second = _quest("duplicate")
    with pytest.raises(ValueError, match="duplicate quest id"):
        available_quests([first, second], [])


def test_quest_progress_initializes_and_completes_all_objectives():
    quest = _quest(
        "ms_004",
        objectives=[
            {"type": "talk_to", "npc": "guild_recruiter_marcus"},
            {"type": "catch_fish", "rarity": "uncommon", "count": 3},
        ],
    )
    state = initialize_progress(quest)

    assert state.status == "in_progress"
    assert state.objectives["0"].target == 1
    assert state.objectives["1"].target == 3

    state = update_objective_progress(state, "0", 1)
    assert state.status == "in_progress"
    assert state.objectives["0"].completed

    state = update_objective_progress(state, "1", 99)
    assert state.completed
    assert state.objectives["1"].current == 3
    assert state.objectives["1"].completed


def test_quest_progress_is_monotonic_and_rejects_invalid_updates():
    state = initialize_progress(_quest("sq_001"))
    state = update_objective_progress(state, "0", 1)
    unchanged = update_objective_progress(state, "0", 0)
    assert unchanged.objectives["0"].current == 1

    with pytest.raises(ValueError, match="must not be negative"):
        update_objective_progress(state, "0", -1)
    with pytest.raises(KeyError, match="unknown quest objective"):
        update_objective_progress(state, "missing", 1)


def test_reward_plan_separates_mutations_from_domain_signals():
    plan = reward_plan(
        {
            "gold": 400,
            "xp": 600,
            "item": "rescue_medal",
            "title": "Storm Rescuer",
            "reputation": {"port_authority": 15},
            "unlock": "deep_water_fishing",
        }
    )

    assert plan.increments == {"gold": 400, "xp": 600}
    assert plan.items == ("rescue_medal",)
    assert plan.titles == ("Storm Rescuer",)
    assert plan.signals == {
        "reputation": {"port_authority": 15},
        "unlock": "deep_water_fishing",
    }


def test_daily_and_weekly_selection_preserves_source_order_and_limits():
    quests = [
        _quest("d1", type="daily"),
        _quest("d2", type="daily"),
        _quest("w1", type="weekly"),
        _quest("d3", type="daily"),
    ]

    assert [quest.id for quest in select_quests_by_type(quests, "daily", limit=2)] == [
        "d1",
        "d2",
    ]
    assert [quest.id for quest in select_quests_by_type(quests, "weekly", limit=3)] == [
        "w1"
    ]
