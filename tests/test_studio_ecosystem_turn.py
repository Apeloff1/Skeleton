from dataclasses import replace
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_scene import scene_catalog
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest, StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_turn import apply_story_turn, verify_story_turn

@pytest.mark.parametrize("pid",[
 "studio_aerial_traversal_amber_highlands",
 "studio_arena_fighting_glacial_fjord",
])
def test_story_turn_replays_real_scene_stage_and_does_not_forge_effects(pid):
    docs=read_blueprint(pid)
    scene=scene_catalog(docs)
    session=start_quest(docs,authorized=True)
    first=scene[0]
    authored=(docs["quest"].get("stage_graph") or docs["quest"]["stages"])[0]["alternatives"][0]
    turn=apply_story_turn(docs,session,scene_id=first["scene_id"],object_id=first["objects"][0],
                          stage=first["quest_stage"],alternative=authored,authorized=True)
    verify_story_turn(docs,session,turn,scene_id=first["scene_id"],object_id=first["objects"][0],
                      stage=first["quest_stage"],alternative=authored)
    assert turn.quest.completed == (first["quest_stage"],)
    assert turn.intent["object_interaction_performed"] is False
    assert not turn.progress["release_certified"]
    with pytest.raises(StudioQuestError):
        apply_story_turn(docs,session,scene_id=scene[1]["scene_id"],
                         object_id=scene[1]["objects"][0],stage=first["quest_stage"],
                         alternative=authored,authorized=True)
    with pytest.raises(StudioQuestError):
        verify_story_turn(docs,session,replace(turn,previous_quest_digest="0"*64),
                          scene_id=first["scene_id"],object_id=first["objects"][0],
                          stage=first["quest_stage"],alternative=authored)
