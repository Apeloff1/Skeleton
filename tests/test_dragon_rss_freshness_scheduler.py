"""RSS Updates hatchling: host fairness, durable retries, preemption, tamper alarms."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_rss_freshness_scheduler import (
    DragonRssFreshnessScheduler,
)
from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)


KEY = b"operator-owned-rss-state-key-32-or-more-bytes"
A = "source-"+"a"*64
B = "source-"+"b"*64
C = "source-"+"c"*64


def _ticket(source=A, url="https://feeds.example/rss.xml"):
    return HatchlingWorkerTicket(
        "studio", "updates", source, url,
        "hatchling:updates-1", "d"*64,
        "2026-10-12T00:00:00Z", "2026-10-12T00:00:30Z",
    )


def _admission(allowed=True):
    w = object.__new__(DragonNestWorkerAdmission)
    calls = []
    w.authorize_chunk = lambda *args, **kwargs: (
        calls.append((args, kwargs)) or allowed)
    return w, calls


def _subscribe(q):
    q.subscribe("studio", A, "https://feeds.example/rss.xml",
                policy_receipt_digest="1"*64, priority=5,
                period_seconds=3600, now=100, operator_authorized=True)
    q.subscribe("studio", B, "https://feeds.example/other.xml",
                policy_receipt_digest="2"*64, priority=5,
                period_seconds=3600, now=100, operator_authorized=True)
    q.subscribe("studio", C, "https://another.example/atom.xml",
                policy_receipt_digest="3"*64, priority=4,
                period_seconds=3600, now=100, operator_authorized=True)


def test_rss_due_queue_is_tenant_scoped_host_fair_and_never_fetches():
    with sqlite3.connect(":memory:") as db:
        q = DragonRssFreshnessScheduler(db, signing_key=KEY)
        _subscribe(q)
        due = q.due("studio", now=100, per_host=1, authorized=True)
        assert due["schema"]=="skeleton.dragon.rss_due_workboard.v1"
        assert due["total_due"]==3
        assert due["selected_count"]==2
        assert {entry["host"] for entry in due["selected"]}=={
            "feeds.example", "another.example"}
        assert all(not item["crawler_authorized"] for item in due["selected"])
        assert all(item["separate_fresh_rights_verification_required"]
                   for item in due["selected"])
        assert due["network_requests"]==due["workers_started"]==0
        all_due=q.due("studio", now=100, per_host=2, authorized=True)
        assert all_due["selected_count"]==3
        assert q.due("other-owner", now=100, authorized=True)["selected"]==[]
        with pytest.raises(PermissionError):
            q.due("studio", now=100, authorized=False)
        assert q.due("studio", now=99, authorized=True)["total_due"]==0


def test_rss_record_requires_idle_worker_and_cas_and_backoff():
    with sqlite3.connect(":memory:") as db:
        q = DragonRssFreshnessScheduler(db, signing_key=KEY)
        _subscribe(q)
        worker, calls = _admission()
        result=q.record_poll(
            _ticket(), worker, admission_kwargs={},
            expected_revision=1, now=100, succeeded=False,
            snapshot_digest=None, authorized=True)
        assert len(calls)==2
        assert result["revision"]==2 and result["failures"]==1
        assert result["next_due"]>=100+7200
        assert not result["receipt_verified_here"]
        with pytest.raises(PermissionError,match="generation"):
            q.record_poll(
                _ticket(),worker,admission_kwargs={},
                expected_revision=1,now=100,succeeded=False,
                snapshot_digest=None,authorized=True)
        with pytest.raises(PermissionError,match="due time"):
            q.record_poll(
                _ticket(),worker,admission_kwargs={},
                expected_revision=2,now=101,succeeded=False,
                snapshot_digest=None,authorized=True)
        next_result=q.record_poll(
            _ticket(),worker,admission_kwargs={},
            expected_revision=2,now=result["next_due"],succeeded=False,
            snapshot_digest=None,authorized=True)
        assert next_result["failures"]==2
        assert next_result["next_due"]-result["next_due"]>=14400
        reset=q.record_poll(
            _ticket(),worker,admission_kwargs={},
            expected_revision=3,now=next_result["next_due"],succeeded=True,
            snapshot_digest="e"*64,authorized=True)
        assert reset["failures"]==0 and reset["revision"]==4
        assert reset["next_due"]-next_result["next_due"]>=3600
        assert q.due("studio", now=reset["next_due"]-1,authorized=True)["total_due"]==2
        refused, _ = _admission(False)
        with pytest.raises(PermissionError,match="idle worker"):
            q.record_poll(
                _ticket(),refused,admission_kwargs={},
                expected_revision=4,now=reset["next_due"],succeeded=False,
                snapshot_digest=None,authorized=True)


def test_rss_journal_detects_state_and_history_tampering_across_restart(tmp_path):
    filename = tmp_path/"rss.sqlite"
    with sqlite3.connect(filename) as db:
        q = DragonRssFreshnessScheduler(db, signing_key=KEY)
        _subscribe(q)
        assert q.due("studio",now=100,authorized=True)["total_due"]==3
    with sqlite3.connect(filename) as db:
        q = DragonRssFreshnessScheduler(db, signing_key=KEY)
        assert q.due("studio",now=100,authorized=True)["selected_count"]==2
        prior=db.execute(
            "SELECT state FROM dragon_rss_schedule_v1 "
            "WHERE owner=? AND source_id=?",("studio",A)).fetchone()[0]
        db.execute(
            "UPDATE dragon_rss_schedule_v1 SET state='{}' "
            "WHERE owner=? AND source_id=?",("studio",A))
        with pytest.raises(ValueError,match="head"):
            q.due("studio",now=100,authorized=True)
        db.execute(
            "UPDATE dragon_rss_schedule_v1 SET state=? "
            "WHERE owner=? AND source_id=?",(prior,"studio",A))
    with sqlite3.connect(filename) as db:
        db.execute(
            "DELETE FROM dragon_rss_schedule_events_v1 "
            "WHERE owner=? AND source_id=? AND sequence=1",("studio", B))
        q = DragonRssFreshnessScheduler(db,signing_key=KEY)
        with pytest.raises(ValueError,match="chain"):
            q.due("studio",now=100,authorized=True)


def test_rss_rejects_bad_sources_or_missing_operator_permissions():
    with sqlite3.connect(":memory:") as db:
        q=DragonRssFreshnessScheduler(db,signing_key=KEY)
        for url in ("http://feeds.example/rss",
                    "https://alice:pw@feeds.example/rss",
                    "https://feeds.example/rss#fragment"):
            with pytest.raises(ValueError,match="HTTPS"):
                q.subscribe("studio",A,url,
                            policy_receipt_digest="1"*64,
                            priority=4,period_seconds=3600,now=100,
                            operator_authorized=True)
        with pytest.raises(PermissionError,match="operator"):
            q.subscribe("studio",A,"https://feeds.example/rss",
                        policy_receipt_digest="1"*64,priority=4,
                        period_seconds=3600,now=100,operator_authorized=False)
        q.subscribe("studio",A,"https://feeds.example/rss.xml",
                    policy_receipt_digest="1"*64,priority=5,
                    period_seconds=3600,now=100,operator_authorized=True)
        with pytest.raises(ValueError,match="already"):
            q.subscribe("studio",A,"https://feeds.example/rss.xml",
                        policy_receipt_digest="1"*64,priority=5,
                        period_seconds=3600,now=101,operator_authorized=True)
