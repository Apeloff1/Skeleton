import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_fence import pin_source_sections
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_preview_worker import compile_and_spool_preview

@pytest.mark.parametrize("project", [
 "studio_aerial_traversal_amber_highlands",
 "studio_arena_fighting_glacial_fjord",
])
def test_compiles_actual_offline_html5_proof_without_native_genre_claim(tmp_path,project):
    root=tmp_path/"secure"
    root.mkdir(mode=0o700)
    docs=read_blueprint(project)
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    spool=ArtifactSpool(root,authorized=True)
    receipt=compile_and_spool_preview(journal,spool,authorized=True)
    assert receipt["winning_replay_proven_in_grid"] is True
    assert spool.verify(receipt["html_sha256"])==receipt["html_bytes"]
    assert not receipt["target_genre_implemented"]
    assert not receipt["consumer_release_certified"]
    with pytest.raises(PermissionError):
        compile_and_spool_preview(journal,spool,authorized=False)
