"""Gameplay assurance executes seven game production milestones."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionEpisode, ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile, author_archipelago
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_narrative import original_expedition_story
from skeleton.jeeves.game_frontier_expedition_quests import original_quest_book
from skeleton.jeeves.game_frontier_expedition_world_assurance import (
    AXES, compile_world_assurance, verify_world_assurance, resilience,
)


def fixture(seed=19):
    world = author_archipelago("world_assurance", "a"*64, ArchipelagoProfile(seed, islands=5))
    player = original_campaign_player()
    story = original_expedition_story(world, "c"*64)
    quests = original_quest_book(ExpeditionEpisode(world, player), story)
    return world, player, story, quests


def test_complete_seven_milestone_replay_with_real_state_machine():
    source = fixture()
    report = compile_world_assurance(*source)
    assert set(report["axes"]) == set(AXES)
    assert report["axes_executed"] == 7
    assert report["source_assured"]
    assert not report["production_release_approved"]
    verify_world_assurance(*source, report)
    assert report == compile_world_assurance(*source)


def test_route_and_source_assurance_planes_are_functional():
    world, player, story, quests = fixture()
    axes = compile_world_assurance(world, player, story, quests)["axes"]
    assert axes["geometry"]["nodes"] == len(world.waypoints)
    assert axes["geometry"]["edges"] == len(world.by_edge)
    assert axes["geometry"]["euclidean_sum_m"] > 0
    assert not axes["geometry"]["physical_gps_used"]
    assert world.arrival in axes["connectivity"]["reachable"]
    assert axes["connectivity"]["reachable"] == axes["adversarial"]["reachable"]
    assert len(axes["playthrough"]["winning_game_routes"]) == len(world.destinations)
    for route in axes["playthrough"]["winning_game_routes"]:
        assert len(route["steps"]) == len(route["edges"])
    assert axes["capability"]["one_at_a_time_probes"]
    assert axes["canon"]["scene_count"] > 0
    assert axes["canon"]["quest_stages"] > 0
    assert len(axes["canon"]["available_endings"]) >= 2
    assert not axes["canon"]["orphaned_references"]


def test_bounded_resilience_and_forgery_denial():
    world, player, story, quests = fixture()
    assert len(resilience(world, max_probes=3)["checked_edges"]) <= 3
    with pytest.raises(ExpeditionError, match="finite"):
        resilience(world, max_probes=0)
    report = compile_world_assurance(world, player, story, quests)
    altered = deepcopy(report)
    altered["axes"]["connectivity"]["reachable"] = []
    with pytest.raises(ExpeditionError, match="differs"):
        verify_world_assurance(world, player, story, quests, altered)
    other, _, _, _ = fixture(23)
    with pytest.raises(ExpeditionError, match="foreign"):
        compile_world_assurance(other, player, story, quests)


def test_campaign_artifact_integrates_all_seven_and_independent_rebuild():
    from skeleton.jeeves.game_frontier_expedition_campaign import (
        compile_original_campaign, verify_original_campaign,
    )
    candidate = compile_original_campaign("world_assurance", gdd_digest="c"*64,
                                          seed=19, islands=5)
    assert candidate["world_assurance"]["axes_executed"] == 7
    assert candidate["manifest"]["world_assurance_receipt"] == (
        candidate["world_assurance"]["receipt_digest"])
    assert "game/frontier/world_assurance.json" in candidate["files"]
    assert verify_original_campaign(
        candidate, project_id="world_assurance", gdd_digest="c"*64,
        seed=19, islands=5)["all_source_bytes_verified"]
