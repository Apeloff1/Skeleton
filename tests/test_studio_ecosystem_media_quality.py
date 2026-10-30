import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_offline_bundle import build_offline_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_media_quality import inspect_rendered_media

def test_measured_original_svg_and_wav_preview_quality(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    export=tmp_path/"export"
    export.mkdir(mode=0o700)
    owner=StudioPortfolio(root,authorized=True)
    pid="studio_arena_fighting_glacial_fjord"
    supervisor=owner.open(pid,authorized=True)
    bundle=build_offline_studio_bundle(supervisor.journal,supervisor.spool,export,
                                       authorized=True)
    signal=inspect_rendered_media(export/pid,authorized=True)
    assert signal["svg_geometry_elements"]>=28
    assert signal["audio_frame_count"]==48000
    assert 0<signal["audio_peak_fraction"]<1
    assert signal["audio_rms_fraction"]>0
    assert not signal["artistic_quality_verified"]
