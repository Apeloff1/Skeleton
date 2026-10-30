"""Real-source scene gating is replay-bound, never physical world evidence."""
from dataclasses import replace
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest, step_quest, StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene import scene_catalog, inspect_scene, inspect_object_intent


@pytest.mark.parametrize("pid", ["studio_aerial_traversal_amber_highlands",
                                 "studio_arena_fighting_glacial_fjord"])
def test_scenes_use_both_real_source_schemas_and_live_quest_lock(pid):
    docs = read_blueprint(pid)
    scenes = scene_catalog(docs)
    assert len(scenes) == 3
    session = start_quest(docs, authorized=True)
    unlocked = inspect_scene(session, docs, scene_id=scenes[0]["scene_id"], authorized=True)
    locked = inspect_scene(session, docs, scene_id=scenes[1]["scene_id"], authorized=True)
    assert unlocked["unlocked"] and not locked["unlocked"]
    receipt = inspect_object_intent(session, docs, scene_id=scenes[0]["scene_id"],
                                   object_id=scenes[0]["objects"][0], authorized=True)
    assert receipt["object_interaction_performed"] is False
    with pytest.raises(StudioQuestError):
        inspect_object_intent(session, docs, scene_id=scenes[1]["scene_id"],
                              object_id=scenes[1]["objects"][0], authorized=True)
    stage = docs["quest"].get("stage_graph") or docs["quest"]["stages"]
    session = step_quest(session, docs, stage=stage[0]["id"],
                         alternative=stage[0]["alternatives"][0], authorized=True)
    assert inspect_scene(session, docs, scene_id=scenes[1]["scene_id"], authorized=True)["unlocked"]
    with pytest.raises(StudioQuestError):
        inspect_scene(replace(session, digest="0"*64), docs,
                      scene_id=scenes[1]["scene_id"], authorized=True)
    with pytest.raises(PermissionError):
        inspect_scene(session, docs, scene_id=scenes[1]["scene_id"], authorized=False)
