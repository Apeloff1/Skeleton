"""Atomic RSS Updates hatchling: signed snapshots and durable schedule together."""
from dataclasses import replace
from hashlib import sha256
from unittest.mock import patch
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.webcrawler.dragon_rss_update_queue import (
    DragonRssUpdateQueue, SignedRssSnapshot)
from skeleton.ai.webcrawler.dragon_rss_freshness_scheduler import (
    DragonRssFreshnessScheduler)
from skeleton.ai.webcrawler.dragon_verified_rss_poll import DragonVerifiedRssPoll
from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    HatchlingWorkerTicket, DragonNestWorkerAdmission)

OWNER="studio"
SID="source-"+"a"*64
URL="https://feeds.example/game-updates.xml"
KEY=b"operator-owned-scheduler-hmac-key-more-than-32-bytes"
POLICY="f"*64
RSS=b"""<rss version="2.0"><channel><item><title>New platform devkit article</title><link>https://docs.example/game-engine</link><guid>v3</guid><pubDate>Mon, 12 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>"""


def signer():
    private=Ed25519PrivateKey.generate()
    return private,private.public_key().public_bytes_raw()


def setup(db):
    scheduler=DragonRssFreshnessScheduler(db,signing_key=KEY)
    scheduler.subscribe(
        OWNER,SID,URL,policy_receipt_digest=POLICY,priority=4,
        period_seconds=3600,now=100,operator_authorized=True)
    queue=DragonRssUpdateQueue(db)
    return queue,scheduler,DragonVerifiedRssPoll(queue,scheduler)


def ticket(owner=OWNER,url=URL):
    return HatchlingWorkerTicket(
        owner,"updates",SID,url,"hatchling:updates-1","d"*64,
        "2026-10-12T00:00:00Z","2026-10-12T00:00:30Z")


def receipt(key,*,owner=OWNER,policy=POLICY,xml=RSS,feed=URL):
    r=SignedRssSnapshot(owner,SID,feed,sha256(xml).hexdigest(),
                        100,180,"external-feed-review","external-feed-key",policy,"")
    return replace(r,signature_hex=key.sign(canonical_json(r.body()).encode()).hex())


def worker(max_calls=100):
    w=object.__new__(DragonNestWorkerAdmission)
    calls=[]
    w.authorize_chunk=lambda *args,**kwargs: (
        calls.append((args,kwargs)) or len(calls)<=max_calls)
    return w,calls


def call_args(key,pub,admission,**extra):
    result=dict(ticket=ticket(),admission=admission,xml=RSS,receipt=receipt(key),
                reviewer_public_key=pub,trusted_issuer="external-feed-review",
                key_id="external-feed-key",admission_kwargs={},
                expected_revision=1,now=150,authorized=True)
    result.update(extra)
    return result


def test_verified_rss_poll_commits_queue_and_scheduler_together():
    key,pub=signer()
    with sqlite3.connect(":memory:") as db:
        queue,scheduler,operator=setup(db)
        admission,calls=worker()
        report=operator.accept(**call_args(key,pub,admission))
        assert report["schema"]=="skeleton.dragon.atomic_verified_rss_poll.v1"
        assert report["new_unverified_research_leads"]==1
        assert report["candidate_research_items"]==1
        assert report["poll_revision"]==2
        assert len(report["handoff_digest"])==64
        assert len(calls)>=5
        assert report["atomic_commit"] and report["idle_ticket_rechecked"]
        assert report["network_requests"]==0
        assert not report["training_authorized"]
        assert not report["weights_promoted"]
        pending=queue.pending(OWNER,authorized=True)
        assert pending["count"]==1
        assert pending["entries"][0]["review_status"]=="unverified_update_lead"
        assert scheduler._current(OWNER,SID)["revision"]==2
        assert scheduler.due(OWNER,now=150,authorized=True)["selected_count"]==0
        assert queue.pending("another-tenant",authorized=True)["count"]==0


def test_verified_rss_poll_rolls_back_snapshot_if_scheduler_fails():
    key,pub=signer()
    with sqlite3.connect(":memory:") as db:
        queue,scheduler,operator=setup(db)
        admission,_=worker()
        with patch.object(scheduler,"record_poll",side_effect=RuntimeError("disk crash")):
            with pytest.raises(RuntimeError,match="disk crash"):
                operator.accept(**call_args(key,pub,admission))
        assert scheduler._current(OWNER,SID)["revision"]==1
        assert queue.pending(OWNER,authorized=True)["count"]==0
        assert db.execute("SELECT COUNT(*) FROM dragon_rss_poll_v1").fetchone()[0]==0
        ok=operator.accept(**call_args(key,pub,admission))
        assert ok["new_unverified_research_leads"]==1


def test_verified_rss_poll_preempted_at_final_commit_rolls_back_both():
    key,pub=signer()
    with sqlite3.connect(":memory:") as db:
        queue,scheduler,operator=setup(db)
        admission,calls=worker(max_calls=4)
        with pytest.raises(PermissionError,match="preempted"):
            operator.accept(**call_args(key,pub,admission))
        assert len(calls)==5
        assert scheduler._current(OWNER,SID)["revision"]==1
        assert queue.pending(OWNER,authorized=True)["entries"]==[]
        assert db.execute("SELECT COUNT(*) FROM dragon_rss_poll_v1").fetchone()[0]==0


@pytest.mark.parametrize("mutation",[
    {"expected_revision":0},
    {"now":99},
    {"ticket":ticket(owner="foreign-owner")},
    {"ticket":ticket(url="https://different.example/feed")},
    {"authorized":False},
    {"receipt":None},
])
def test_verified_rss_poll_rejects_stale_or_wrong_source_without_committing(mutation):
    key,pub=signer()
    with sqlite3.connect(":memory:") as db:
        queue,scheduler,operator=setup(db)
        w,_=worker()
        arguments=call_args(key,pub,w)
        arguments.update(mutation)
        with pytest.raises((PermissionError,TypeError,ValueError)):
            operator.accept(**arguments)
        assert scheduler._current(OWNER,SID)["revision"]==1
        assert queue.pending(OWNER,authorized=True)["entries"]==[]


def test_verified_rss_poll_requires_exact_policy_and_valid_signature():
    key,pub=signer()
    stranger,_=signer()
    with sqlite3.connect(":memory:") as db:
        queue,scheduler,operator=setup(db)
        w,_=worker()
        for invalid in (
            receipt(key,policy="e"*64),
            receipt(stranger),
            replace(receipt(key),body_sha256="0"*64),
            receipt(key,owner="another-tenant"),
        ):
            with pytest.raises((PermissionError,ValueError)):
                operator.accept(**call_args(key,pub,w,receipt=invalid))
        assert queue.pending(OWNER,authorized=True)["count"]==0
        assert scheduler._current(OWNER,SID)["revision"]==1


def test_verified_rss_poll_rejects_unsafe_double_database():
    with sqlite3.connect(":memory:") as db1,sqlite3.connect(":memory:") as db2:
        q=DragonRssUpdateQueue(db1)
        schedule=DragonRssFreshnessScheduler(db2,signing_key=KEY)
        with pytest.raises(TypeError,match="share one canonical"):
            DragonVerifiedRssPoll(q,schedule)
