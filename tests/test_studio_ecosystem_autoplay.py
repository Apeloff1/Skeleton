import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_autoplay import simulate_complete_walk
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import replay_walk


@pytest.mark.parametrize("pid",[
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_all_authored_2d_episodes_have_really_replayable_end_to_end_routes(pid):
    docs = read_blueprint(pid)
    report = simulate_complete_walk(docs, authorized=True)
    session = replay_walk(docs, report["actions"], authorized=True)
    assert session.digest == report["walk_session_sha256"]
    assert session.scene_index == 3
    assert report["all_authored_stages_reached"]
    assert len(report["stage_routes"]) == 3
    assert report["movement_steps"] > 0
    assert not report["real_playtester_verified"]


def test_invalid_override_fails_without_inventing_quest_solution():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    with pytest.raises(ValueError):
        simulate_complete_walk(docs, choice_by_stage={"unknown-stage":"never"},
                               authorized=True)
    with pytest.raises(ValueError):
        simulate_complete_walk(docs, choice_by_stage={"arrival":"unknown-choice"},
                               authorized=True)
