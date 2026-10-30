"""Durable journal validates work graph, owner and source across reopen."""
from pathlib import Path
import sqlite3
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal, checked_graph
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def _owner(tmp_path: Path):
    store=tmp_path/"private"
    store.mkdir(mode=0o700)
    graph=build_work_graph(read_blueprint("studio_arena_fighting_glacial_fjord"))
    return store,graph

def test_sqlite_journal_reopens_with_source_pinned_claims(tmp_path):
    root,graph=_owner(tmp_path)
    s=WorkJournal(root,graph,authorized=True)
    assert s.snapshot()["tasks"]["source-canon"]["status"]=="pending"
    s.claim("source-canon",worker="worker-1",token="token-1",authorized=True)
    reopened=WorkJournal(root,graph,authorized=True)
    assert reopened.snapshot()["tasks"]["source-canon"]["status"]=="leased"
    with pytest.raises(StudioQuestError):
        reopened.claim("quest-integration",worker="worker-2",token="token-2",authorized=True)
    with pytest.raises(StudioQuestError):
        reopened.claim("source-canon",worker="worker-1",token="token-3",authorized=True)
    with pytest.raises(PermissionError):
        WorkJournal(root,graph,authorized=False)

def test_source_drift_and_symlink_workspaces_fail_closed(tmp_path):
    root,graph=_owner(tmp_path)
    WorkJournal(root,graph,authorized=True)
    import copy
    mutated=copy.deepcopy(graph)
    mutated["work_graph_sha256"]="0"*64
    with pytest.raises(StudioQuestError):
        WorkJournal(root,mutated,authorized=True)
    other=build_work_graph(read_blueprint("studio_aerial_traversal_amber_highlands"))
    with pytest.raises(StudioQuestError):
        WorkJournal(root,other,authorized=True)
    link=tmp_path/"linked"
    link.symlink_to(root,target_is_directory=True)
    with pytest.raises(StudioQuestError):
        WorkJournal(link,graph,authorized=True)

def test_review_does_not_claim_external_proof(tmp_path):
    root,graph=_owner(tmp_path)
    store=WorkJournal(root,graph,authorized=True)
    store.claim("source-canon",worker="maker",token="once",authorized=True)
    with pytest.raises(StudioQuestError):
        store.submit("source-canon",worker="impostor",token="once",
                     artifact_sha256="a"*64,authorized=True)
    store.submit("source-canon",worker="maker",token="once",
                 artifact_sha256="a"*64,authorized=True)
    with pytest.raises(StudioQuestError):
        store.review("source-canon",reviewer="maker",accepted=True,authorized=True)
    store.review("source-canon",reviewer="independent",accepted=True,authorized=True)
    assert store.snapshot()["tasks"]["source-canon"]["status"]=="reviewed_claim"
    assert store.snapshot()["completion_evidence_verified"] is False
    store.claim("quest-integration",worker="second",token="next",authorized=True)
