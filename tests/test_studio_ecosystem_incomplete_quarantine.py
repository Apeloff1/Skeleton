import pytest
from skeleton.ai.game_builder.studio_ecosystem_incomplete_quarantine import quarantine_incomplete_bundle
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_manual_quarantine_preserves_partial_user_data(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    pid="studio_arena_fighting_glacial_fjord"
    partial=root/pid
    partial.mkdir(mode=0o700)
    (partial/"index.html").write_text("unfinished authoring output")
    receipt=quarantine_incomplete_bundle(root,pid,operator="owner",authorized=True)
    assert receipt["files_deleted"]==0
    assert not partial.exists()
    from pathlib import Path
    assert (Path(receipt["preserved_directory"])/"index.html").read_text()=="unfinished authoring output"

def test_manifest_cannot_be_quarantined_as_unfinished(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    pid="studio_arena_fighting_glacial_fjord"
    dest=root/pid
    dest.mkdir(mode=0o700)
    (dest/"manifest.json").write_bytes(b"{}")
    with pytest.raises(StudioQuestError):
        quarantine_incomplete_bundle(root,pid,operator="owner",authorized=True)
