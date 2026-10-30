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

def test_created_journal_file_is_private(tmp_path):
    import os
    root,graph=_owner(tmp_path)
    WorkJournal(root,graph,authorized=True)
    if os.name=="posix":
        assert (root/"studio_work.sqlite3").stat().st_mode & 0o077 == 0

def test_event_integrity_detects_modified_durable_history(tmp_path):
    root,graph=_owner(tmp_path)
    journal=WorkJournal(root,graph,authorized=True)
    journal.claim("source-canon",worker="maker",token="one",authorized=True)
    proof=journal.verify_events()
    assert proof["events"]==1
    assert len(proof["final_sha256"])==64
    assert proof["external_attestation_verified"] is False
    with sqlite3.connect(root/"studio_work.sqlite3") as db:
        db.execute("UPDATE events SET event_json='{}' WHERE seq=1")
    with pytest.raises(StudioQuestError):
        WorkJournal(root,graph,authorized=True)

def test_crash_recovery_fences_old_worker_token_and_attempt(tmp_path):
    root,graph=_owner(tmp_path)
    journal=WorkJournal(root,graph,authorized=True)
    journal.claim("source-canon",worker="workerA",token="old",authorized=True)
    restarted=WorkJournal(root,graph,authorized=True)
    restarted.recover_claim("source-canon",former_worker="workerA",
                             expected_attempt=1,operator="supervisor",authorized=True)
    restarted.claim("source-canon",worker="workerB",token="fresh",authorized=True)
    with pytest.raises(StudioQuestError):
        restarted.submit("source-canon",worker="workerA",token="old",
                         artifact_sha256="a"*64,authorized=True)
    with pytest.raises(StudioQuestError):
        restarted.recover_claim("source-canon",former_worker="workerA",
                                expected_attempt=1,operator="supervisor",authorized=True)
    restarted.submit("source-canon",worker="workerB",token="fresh",
                     artifact_sha256="b"*64,authorized=True)
    assert restarted.verify_events()["events"]==4

def test_rejected_submission_clears_stale_hash_and_requeues(tmp_path):
    root,graph=_owner(tmp_path)
    s=WorkJournal(root,graph,authorized=True)
    s.claim("source-canon",worker="maker",token="old",authorized=True)
    s.submit("source-canon",worker="maker",token="old",
             artifact_sha256="b"*64,authorized=True)
    s.review("source-canon",reviewer="reviewer",accepted=False,authorized=True)
    row=s.snapshot()["tasks"]["source-canon"]
    assert row["status"]=="pending"
    assert row["submitted_sha"] is None
    s.claim("source-canon",worker="maker",token="fresh",authorized=True)
    assert s.snapshot()["tasks"]["source-canon"]["attempt"]==2

def test_paused_admission_persists_across_restarts(tmp_path):
    root,graph=_owner(tmp_path)
    j=WorkJournal(root,graph,authorized=True)
    j.set_paused(True,operator="supervisor",authorized=True)
    next_j=WorkJournal(root,graph,authorized=True)
    with pytest.raises(StudioQuestError):
        next_j.claim("source-canon",worker="w",token="t",authorized=True)
    next_j.set_paused(False,operator="supervisor",authorized=True)
    next_j.claim("source-canon",worker="w",token="t",authorized=True)
    assert next_j.verify_events()["events"]==3

def test_event_replay_rejects_task_row_forgery_even_when_chain_is_intact(tmp_path):
    root,graph=_owner(tmp_path)
    j=WorkJournal(root,graph,authorized=True)
    j.claim("source-canon",worker="worker",token="token",authorized=True)
    assert j.verify_state()["local_lifecycle_replay_valid"]
    with sqlite3.connect(root/"studio_work.sqlite3") as db:
        db.execute("UPDATE tasks SET status='reviewed_claim' WHERE id='source-canon'")
    with pytest.raises(StudioQuestError):
        WorkJournal(root,graph,authorized=True)
