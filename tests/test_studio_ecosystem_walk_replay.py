import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
    start_walk, walk_action, replay_walk, verify_walk,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


@pytest.mark.parametrize("project", [
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_actual_collision_and_proximity_bound_original_scene_actions(project):
    docs = read_blueprint(project)
    session = start_walk(docs, authorized=True)
    assert session.position == (1, 1)
    with pytest.raises(StudioQuestError):
        walk_action(session, docs, action="choose", value="anything", authorized=True)
    with pytest.raises(StudioQuestError):
        walk_action(session, docs, action="move", value="up", authorized=True)
    for _ in range(13):
        session = walk_action(session, docs, action="move",
                              value="right", authorized=True)
    for _ in range(7):
        session = walk_action(session, docs, action="move",
                              value="down", authorized=True)
    assert session.position == (14, 8)
    from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
    option = playable_world_source(docs)["stages"][0]["alternatives"][0]
    session = walk_action(session, docs, action="choose",
                          value=option, authorized=True)
    assert session.scene_index == 1
    assert session.position == (1, 1)
    assert len(session.chosen) == 1
    verify_walk(session, docs)
    assert replay_walk(docs, list(session.events), authorized=True) == session
    assert session.receipt()["release_certified"] is False


def test_no_forged_end_state_or_unauthorized_replay():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    with pytest.raises(StudioQuestError):
        replay_walk(docs, [("move", "left")], authorized=True)
    with pytest.raises(StudioQuestError):
        replay_walk(docs, [("move", "teleport")], authorized=True)
    with pytest.raises(PermissionError):
        replay_walk(docs, [], authorized=False)
