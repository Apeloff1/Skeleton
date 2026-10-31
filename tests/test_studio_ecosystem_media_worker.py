import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_fence import pin_source_sections
from skeleton.ai.game_builder.studio_ecosystem_media_worker import render_media_packet
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid",[
 "studio_aerial_traversal_amber_highlands",
 "studio_puzzle_expedition_copper_mesa",
 "studio_arena_fighting_glacial_fjord",
])
def test_canonical_sources_render_real_bytes_and_store_them(tmp_path,pid):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    docs=read_blueprint(pid)
    j=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(j,docs,authorized=True)
    spool=ArtifactSpool(root,authorized=True)
    result=render_media_packet(j,spool,authorized=True)
    assert spool.verify(result["svg_sha256"])==result["svg_bytes"]
    assert spool.verify(result["wav_sha256"])==result["wav_bytes"]
    assert result["local_svg_and_wav_rendered"]
    assert not result["source_rights_approved"]
    with pytest.raises(StudioQuestError):
        render_media_packet(j,spool,cue_id="fake",authorized=True)
