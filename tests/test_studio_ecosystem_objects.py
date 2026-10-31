import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_objects import object_inventory, resolve_object
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid,object_id",[
 ("studio_aerial_traversal_amber_highlands","hazard_monitor"),
 ("studio_arena_fighting_glacial_fjord","survey_beacon"),
])
def test_authored_objects_have_exact_scene_ownership(pid,object_id):
    docs=read_blueprint(pid)
    report=object_inventory(docs)
    assert report["unique_object_count"] >= 3
    found=resolve_object(docs,object_id)
    assert len(found["scenes"])==1
    assert found["assets_generated"] is False
    with pytest.raises(StudioQuestError):
        resolve_object(docs,"nonexistent_prop")
    assert not report["release_certified"]
