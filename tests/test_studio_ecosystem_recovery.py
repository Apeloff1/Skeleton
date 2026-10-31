import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_recovery import inspect_resumption
from skeleton.ai.game_builder.studio_ecosystem_fence import pin_source_sections

def test_crash_recovery_lists_orphans_without_automatic_takeover(tmp_path):
    root=tmp_path/"secure"
    root.mkdir(mode=0o700)
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    j=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(j,docs,authorized=True)
    spool=ArtifactSpool(root,authorized=True)
    j.claim("source-canon",worker="abandoned",token="stale",authorized=True)
    reopened=WorkJournal(root,build_work_graph(docs),authorized=True)
    status=inspect_resumption(reopened,spool,authorized=True)
    assert status["leases_requiring_manual_recovery"][0]["worker"]=="abandoned"
    assert status["tasks_auto_released"]==0
    assert status["recovery_safe_for_review"] is False
    assert status["release_certified"] is False
    with pytest.raises(PermissionError):
        inspect_resumption(reopened,spool,authorized=False)
