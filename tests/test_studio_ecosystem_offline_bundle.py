import json
from pathlib import Path
import wave
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_fence import pin_source_sections
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_offline_bundle import build_offline_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("project",["studio_aerial_traversal_amber_highlands",
                                   "studio_puzzle_expedition_copper_mesa"])
def test_playable_offline_bundle_has_real_media_and_no_release_claim(tmp_path,project):
    workspace=tmp_path/"secure"
    workspace.mkdir(mode=0o700)
    output=tmp_path/"output"
    output.mkdir(mode=0o700)
    docs=read_blueprint(project)
    j=WorkJournal(workspace,build_work_graph(docs),authorized=True)
    pin_source_sections(j,docs,authorized=True)
    spool=ArtifactSpool(workspace,authorized=True)
    proof=build_offline_studio_bundle(j,spool,output,authorized=True)
    target=Path(proof["output_dir"])
    assert all((target/name).is_file() for name in proof["assets"])
    manifest=json.loads((target/"manifest.json").read_text())
    assert manifest["grid_winning_replay_verified"]
    assert not manifest["target_genre_implemented"]
    assert not manifest["release_certified"]
    assert b"<iframe" in (target/"studio.html").read_bytes()
    with wave.open(str(target/"soundscape.wav"),"rb") as stream:
        assert stream.getnchannels()==1
    with pytest.raises(StudioQuestError):
        build_offline_studio_bundle(j,spool,output,authorized=True)

def test_interactive_story_package_contains_six_owned_files(tmp_path):
    workspace=tmp_path/"source";workspace.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    docs=read_blueprint("studio_aerial_traversal_amber_highlands")
    journal=WorkJournal(workspace,build_work_graph(docs),authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    result=build_offline_studio_bundle(journal,ArtifactSpool(workspace,authorized=True),
                                       out,interactive_story=True,authorized=True)
    target=Path(result["output_dir"])
    assert len(result["assets"])==6
    assert (target/"quest.html").is_file()
    assert json.loads((target/"manifest.json").read_text())["schema"].endswith(".v2")

def test_v3_package_has_real_walkable_canvas_as_seventh_file(tmp_path):
    workspace=tmp_path/"private";workspace.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    j=WorkJournal(workspace,build_work_graph(docs),authorized=True)
    pin_source_sections(j,docs,authorized=True)
    bundle=build_offline_studio_bundle(
        j,ArtifactSpool(workspace,authorized=True),out,
        walkable_story=True,authorized=True)
    target=Path(bundle["output_dir"])
    assert len(bundle["assets"])==7
    assert b"<canvas" in (target/"walkable.html").read_bytes()
    manifest=json.loads((target/"manifest.json").read_bytes())
    assert manifest["schema"]=="skeleton.game_builder.studio_offline_package.v3"
