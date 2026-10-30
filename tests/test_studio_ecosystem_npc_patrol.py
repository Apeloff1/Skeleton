import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_npc_patrol import (
    cast_patrols,inspect_npc_contact,
)
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid",[
 "studio_aerial_traversal_amber_highlands",
 "studio_puzzle_expedition_copper_mesa",
 "studio_arena_fighting_glacial_fjord",
])
def test_real_original_cast_patrols_are_reachable_and_repeatable(pid):
    docs=read_blueprint(pid)
    world=playable_world_source(docs)
    first=cast_patrols(docs)
    assert first==cast_patrols(docs)
    assert first["actors"]
    for actor in first["actors"]:
        assert actor["name"] and actor["knows"]
        for x,y in actor["patrol"]:
            assert world["maps"][0][y][x]=="."
    start=first["actors"][0]
    receipt=inspect_npc_contact(docs,npc_id=start["id"],
                                player_position=tuple(start["patrol"][0]),
                                accepted_moves=0,authorized=True)
    assert receipt["local_contact_available"]
    assert not receipt["real_dialogue_performed"]
    with pytest.raises(StudioQuestError):
        inspect_npc_contact(docs,npc_id="no-one",
                            player_position=(1,1),accepted_moves=0,authorized=True)
