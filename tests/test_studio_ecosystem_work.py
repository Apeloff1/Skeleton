import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph, ready_work
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid",["studio_aerial_traversal_amber_highlands",
                                "studio_arena_fighting_glacial_fjord"])
def test_real_production_graph_requires_review_before_execution(pid):
    g=build_work_graph(read_blueprint(pid))
    assert g["tasks"][-1]["id"]=="release-qualification"
    assert ready_work(g,[],authorized=True)["ready_for_operator_review"]==["source-canon"]
    after=ready_work(g,["source-canon"],authorized=True)
    assert after["ready_for_operator_review"]==["quest-integration"]
    assert not after["completion_evidence_verified"]
    with pytest.raises(StudioQuestError):
        ready_work(g,["release-qualification"],authorized=True)
    with pytest.raises(PermissionError):
        ready_work(g,[],authorized=False)
