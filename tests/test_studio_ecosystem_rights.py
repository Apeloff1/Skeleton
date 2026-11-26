import pytest
from copy import deepcopy
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_rights import release_requirements
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
@pytest.mark.parametrize("pid",[
 "studio_aerial_traversal_amber_highlands",
 "studio_puzzle_expedition_copper_mesa",
 "studio_arena_fighting_glacial_fjord",
])
def test_release_cannot_be_conferred_by_source_metadata(pid):
    report=release_requirements(read_blueprint(pid))
    assert report["unresolved_release_blockers"]
    assert not any(g["verified"] for g in report["quality_gates"])
    assert report["pending_art_jobs"]>0
    assert report["pending_audio_cues"]>0
    assert not report["rights_approved"]
    assert not report["release_certified"]

def test_forged_quality_gate_fails_closed():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["verification"]["quality_gates"][0]["status"]="passed"
    with pytest.raises(StudioQuestError):
        release_requirements(docs)
