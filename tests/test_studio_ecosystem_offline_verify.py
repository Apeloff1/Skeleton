from pathlib import Path
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_fence import pin_source_sections
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_offline_bundle import build_offline_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_offline_verify import verify_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_verify_complete_bundle_then_reject_corrupted_media(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    output=tmp_path/"export"
    output.mkdir(mode=0o700)
    pid="studio_aerial_traversal_amber_highlands"
    docs=read_blueprint(pid)
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    pkg=build_offline_studio_bundle(journal,ArtifactSpool(root,authorized=True),
                                    output,authorized=True)
    target=Path(pkg["output_dir"])
    verified=verify_studio_bundle(target,authorized=True)
    assert verified["local_bundle_integrity_verified"]
    assert verified["files_verified"]==5
    assert not verified["consumer_release_certified"]
    (target/"environment.svg").write_bytes(b"corrupted")
    with pytest.raises(StudioQuestError):
        verify_studio_bundle(target,authorized=True)

def test_verified_v2_story_package_rejects_tampered_quest_page(tmp_path):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    output=tmp_path/"export";output.mkdir(mode=0o700)
    pid="studio_aerial_traversal_amber_highlands"
    docs=read_blueprint(pid)
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    result=build_offline_studio_bundle(journal,ArtifactSpool(root,authorized=True),
                                       output,interactive_story=True,authorized=True)
    target=Path(result["output_dir"])
    assert verify_studio_bundle(target,authorized=True)["files_verified"]==6
    (target/"quest.html").write_bytes(b"forged")
    with pytest.raises(StudioQuestError):
        verify_studio_bundle(target,authorized=True)

def test_v3_walkable_bundle_checks_all_seven_file_digests(tmp_path):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    pid="studio_arena_fighting_glacial_fjord"
    docs=read_blueprint(pid)
    j=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(j,docs,authorized=True)
    built=build_offline_studio_bundle(
        j,ArtifactSpool(root,authorized=True),out,walkable_story=True,
        authorized=True)
    target=Path(built["output_dir"])
    assert verify_studio_bundle(target,authorized=True)["files_verified"]==7
    (target/"walkable.html").write_bytes(b"tampered")
    with pytest.raises(StudioQuestError):
        verify_studio_bundle(target,authorized=True)
