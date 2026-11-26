import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_endings import ending_obligations

@pytest.mark.parametrize("project",["studio_aerial_traversal_amber_highlands",
                                   "studio_arena_fighting_glacial_fjord"])
def test_unimplemented_ending_predicates_are_reported_not_forged(project):
    docs=read_blueprint(project)
    program=ending_obligations(docs)
    assert len(program["endings"])==3
    assert not program["all_endings_mechanically_bound"]
    assert not any(e["sandbox_eligible"] for e in program["endings"])
    q=docs["quest"].get("stage_graph") or docs["quest"]["stages"]
    session=replay_quest(docs,[(s["id"],s["alternatives"][0]) for s in q],authorized=True)
    after=ending_obligations(docs,session)
    assert after["session_digest"]==session.digest
    assert after["endings"][0]["physical_or_rights_evidence_verified"] is False
    assert after["release_certified"] is False
