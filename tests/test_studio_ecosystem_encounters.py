import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_encounters import (
    authored_hazards,replay_hazard_health,
)
from skeleton.ai.game_builder.studio_ecosystem_autoplay import simulate_complete_walk
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid",[
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_source_hazards_preserve_actual_quest_winning_route(pid):
    docs=read_blueprint(pid)
    arrangement=authored_hazards(docs)
    synthetic=simulate_complete_walk(docs,authorized=True)
    receipt=replay_hazard_health(docs,synthetic["actions"],authorized=True)
    assert receipt["remaining_health"]==arrangement["starting_health"]
    assert receipt["hazard_contacts"]==[]
    assert not receipt["native_combat_qualified"]

def test_fake_movement_is_never_accepted_as_hazard_proof():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    with pytest.raises(StudioQuestError):
        replay_hazard_health(docs,[("move","left")],authorized=True)

def test_hazard_replay_never_indexes_an_illegal_post_completion_stage():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    passed=simulate_complete_walk(docs,authorized=True)
    with pytest.raises(StudioQuestError):
        replay_hazard_health(docs,passed["actions"]+[["move","right"]],
                             authorized=True)
