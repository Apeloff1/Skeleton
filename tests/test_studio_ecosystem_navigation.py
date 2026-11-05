import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_navigation import shortest_scene_route
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import DIRECTIONS


@pytest.mark.parametrize("pid", [
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_all_original_scenes_have_deterministic_collision_free_routes(pid):
    docs = read_blueprint(pid)
    world = playable_world_source(docs)
    for index, rows in enumerate(world["maps"]):
        a = shortest_scene_route(docs, scene_index=index, authorized=True)
        b = shortest_scene_route(docs, scene_index=index, authorized=True)
        assert a == b
        x, y = a["start"]
        for direction in a["directions"]:
            dx, dy = DIRECTIONS[direction]
            x += dx
            y += dy
            assert rows[y][x] == "."
        assert [x, y] == a["finish"]
        assert abs(x - world["target"][0]) + abs(y - world["target"][1]) <= 1
        assert a["collision_checked"] is True


def test_invalid_scene_and_wall_refused():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    with pytest.raises(StudioQuestError):
        shortest_scene_route(docs, scene_index=-1, authorized=True)
    with pytest.raises(StudioQuestError):
        shortest_scene_route(docs, scene_index=0, start=(0, 0), authorized=True)
