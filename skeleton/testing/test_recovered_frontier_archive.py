"""Canonical P0-P3 source replay, campaign identity and SQLite archival custody."""
from copy import deepcopy
from dataclasses import replace
import sqlite3
from pathlib import Path

import pytest

from skeleton.app.recovered_evidence import EvidenceError
from skeleton.app.frontier_campaign_source import build_campaign
from skeleton.app.frontier_campaign_archive import append_campaign,audit_archive
from skeleton.app.frontier_campaign_history import GENESIS
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger,CampaignError
from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence


def order(tag="a",cid="campaign"):
    return {"schema":"skeleton.frontier-campaign.order.v1","campaign_id":cid,
            "sessions":[{"session_id":"s1","steps":[
                {"fps":60,"lod_tier":1,"weather_digest":"c"*64,
                 "world":{"source_digest":tag*64,"mesh_vertex_count":20,
                          "mesh_triangle_count":8,"reconstruction_digest":"b"*64,
                          "adapter_id":"candidate"},"percepts":["ridge"],"goal":"summit"}]}]}


def session(sid="s1",tag="a"):
    obj=FrontierSession(sid)
    obj.step(clock=PresentationClock(60),lod_tier=1,weather_digest="c"*64,
             evidence=WorldModelEvidence(tag*64,20,8,"b"*64,"candidate"),
             percepts=("ridge",),goal="summit")
    return obj


def test_session_substitution_and_nested_receipt_tamper_denied():
    a,b=session(),session(tag="d")
    assert a.verify() and b.verify()
    a.admissions[0]=b.admissions[0]
    assert not a.verify()
    a=session()
    original=a.admissions[0]
    a.admissions[0]=replace(original,p2=replace(original.p2,confidence=0.9999))
    assert not a.verify()
    a=session()
    a.replay.session_id="substitution"
    assert not a.verify()


def test_campaign_owns_detached_sessions_and_refuses_duplicate_id():
    a=session()
    ledger=CampaignLedger("campaign")
    ledger.add(a)
    a.admissions.clear()
    assert ledger.verify()
    with pytest.raises(CampaignError):
        ledger.add(session())
    ledger.sessions[0].admissions.clear()
    assert not ledger.verify()


def test_source_reconstruction_and_independent_versions(tmp_path):
    db=tmp_path/"frontier.db"
    first=append_campaign(db,"scope",order(),expected_head=GENESIS,authorized=True)
    second=append_campaign(db,"scope",order("d"),expected_head=first["head"],authorized=True)
    third=append_campaign(db,"scope",order("e","other"),expected_head=second["head"],authorized=True)
    actual=audit_archive(db,"scope",expected_head=third["head"],retention=2,
                         history_limit=2,campaign_id="campaign",authorized=True)
    assert actual["event_count"]==3 and actual["replayed_steps"]==3
    assert len(actual["retained_manifests"])==2 and actual["history_compacted"]==1
    assert len(actual["campaign_matches"])==1
    assert len(actual["recent_diff"]["removed"])==1
    assert not actual["source_events_physically_deleted"]
    assert actual==audit_archive(db,"scope",expected_head=third["head"],retention=2,
                                history_limit=2,campaign_id="campaign",authorized=True)
    full=audit_archive(db,"scope",expected_head=third["head"],retention=3,authorized=True)
    assert len(full["retained_manifests"])==3


def test_stale_writer_and_duplicate_manifest_denied(tmp_path):
    db=tmp_path/"frontier.db"
    first=append_campaign(db,"scope",order(),expected_head=GENESIS,authorized=True)
    for source,head in [(order("d"),GENESIS),(order(),first["head"])]:
        with pytest.raises(EvidenceError):
            append_campaign(db,"scope",source,expected_head=head,authorized=True)
    assert audit_archive(db,"scope",expected_head=first["head"],authorized=True)["event_count"]==1


def test_storage_abort_leaves_prior_head(tmp_path):
    db=tmp_path/"frontier.db"
    first=append_campaign(db,"scope",order(),expected_head=GENESIS,authorized=True)
    conn=sqlite3.connect(db)
    conn.execute("CREATE TRIGGER deny_next BEFORE INSERT ON frontier_archive_events_v1 "
                 "WHEN NEW.sequence=1 BEGIN SELECT RAISE(ABORT,'fixture'); END")
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.IntegrityError):
        append_campaign(db,"scope",order("d"),expected_head=first["head"],authorized=True)
    assert audit_archive(db,"scope",expected_head=first["head"],authorized=True)["event_count"]==1


def test_source_mutation_detected_before_new_append(tmp_path):
    db=tmp_path/"frontier.db"
    first=append_campaign(db,"scope",order(),expected_head=GENESIS,authorized=True)
    from skeleton.app.recovered_evidence import canonical
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE frontier_archive_events_v1 SET source=?",(canonical(order("d")),))
    with pytest.raises(EvidenceError):
        audit_archive(db,"scope",expected_head=first["head"],authorized=True)
    with pytest.raises(EvidenceError):
        append_campaign(db,"scope",order("e"),expected_head=first["head"],authorized=True)


def test_scope_isolated_and_unauthorized_calls_do_not_create_db(tmp_path):
    db=tmp_path/"frontier.db"
    with pytest.raises(PermissionError):
        append_campaign(db,"scope",order(),expected_head=GENESIS,authorized=False)
    assert not db.exists()
    first=append_campaign(db,"one",order(),expected_head=GENESIS,authorized=True)
    assert audit_archive(db,"two",expected_head=GENESIS,authorized=True)["event_count"]==0
    with pytest.raises(EvidenceError):
        audit_archive(db,"two",expected_head=first["head"],authorized=True)


@pytest.mark.parametrize("name",["game_frontier_session.py","game_frontier_campaign.py",
                                  "game_frontier_replay.py","game_frontier_milestone_compose.py"])
def test_mirror_bytes(name):
    root=Path(__file__).resolve().parents[2]/"skeleton"
    assert (root/"jeeves"/name).read_bytes()==(root/"ai"/"agents"/"jeeves"/name).read_bytes()


def test_persistent_db_is_required():
    with pytest.raises(EvidenceError,match="persistent"):
        append_campaign(":memory:","scope",order(),expected_head=GENESIS,authorized=True)


def test_corrupt_source_shape_is_rejected_as_integrity_error(tmp_path):
    db=tmp_path/"frontier.db"
    first=append_campaign(db,"scope",order(),expected_head=GENESIS,authorized=True)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE frontier_archive_events_v1 SET source=?",(b'{}',))
    with pytest.raises(EvidenceError):
        audit_archive(db,"scope",expected_head=first["head"],authorized=True)
