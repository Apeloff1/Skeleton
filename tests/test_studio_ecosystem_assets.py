from copy import deepcopy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_assets import planned_assets
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid",[
 "studio_aerial_traversal_amber_highlands",
 "studio_puzzle_expedition_copper_mesa",
 "studio_arena_fighting_glacial_fjord",
])
def test_all_source_families_produce_real_recipe_jobs(pid):
    report=planned_assets(read_blueprint(pid))
    assert report["jobs"]
    assert report["assets_created"]==0
    assert report["rights_qualified"] is False
    assert report["release_certified"] is False

def test_unearned_asset_complete_state_is_rejected():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["visual"]["asset_recipes"][0]["status"]="complete"
    with pytest.raises(StudioQuestError):
        planned_assets(docs)
