import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest
from skeleton.ai.game_builder.studio_ecosystem_frame import production_frame

@pytest.mark.parametrize("pid",["studio_aerial_traversal_amber_highlands",
                                "studio_arena_fighting_glacial_fjord"])
def test_real_production_frame_joins_source_and_replay_without_fake_proof(pid):
    docs=read_blueprint(pid)
    q=start_quest(docs,authorized=True)
    result=production_frame(docs,q,authorized=True)
    assert len(result["scene_bindings"])==3
    assert len(result["manifest"]["sections"])==8
    assert result["authored_factions"]
    assert result["producer_work"]["tasks"]
    assert result["quest_progress"]["stage_completed"]==0
    assert not result["native_genre_runtime_verified"]
    assert not result["release_certified"]
    with pytest.raises(PermissionError):
        production_frame(docs,q,authorized=False)
