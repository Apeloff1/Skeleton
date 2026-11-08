import pytest
from skeleton.ai.game_builder.studio_ecosystem_supervisor import StudioSupervisor
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_supervisor_is_source_fenced_and_restart_safe(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    project="studio_arena_fighting_glacial_fjord"
    s=StudioSupervisor(root,project,authorized=True)
    s.claim("source-canon",worker="worker",token="one",authorized=True)
    receipt=s.submit("source-canon",worker="worker",token="one",
                     chunks=[b"stage1",b"stage2"],authorized=True)
    assert receipt["local_content_integrity_verified"]
    review=s.review("source-canon",reviewer="reviewer",accepted=True,authorized=True)
    assert review["review_accepted_as_claim"]
    restarted=StudioSupervisor(root,project,authorized=True)
    assert restarted.resume(authorized=True)["recovery_safe_for_review"]
    restarted.claim("quest-integration",worker="second",token="two",authorized=True)
    assert restarted.resume(authorized=True)["leases_requiring_manual_recovery"]
    with pytest.raises(PermissionError):
        restarted.submit("quest-integration",worker="second",token="two",
                         chunks=[b"x"],authorized=False)
