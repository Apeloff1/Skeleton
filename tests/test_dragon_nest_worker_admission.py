"""Global resource tickets for idle Dragon research (zero network calls)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import sqlite3

import pytest

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_technical_source_atlas import DragonTechnicalSources
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)
from skeleton.ai.webcrawler.dragon_resource_session import (
    DragonResourceSession, HardwareSample, SessionTask,
)
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourceScheduler, GlobalResourcePolicy, PlanePolicy, ResourceVector,
)

OWNER = "worker-owner"
T0 = "2026-10-12T12:00:00Z"
T2 = "2026-10-12T12:15:00Z"
T3 = "2026-10-12T12:16:01Z"


def hw(at=1000, pressure=.1, thermal=False):
    return HardwareSample(512*1024**2,8,pressure,.75,True,thermal,float(at))


def ledger():
    return GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=2000,memory_mb=128,io_tokens=100),
        (PlanePolicy("interactive",2,ResourceVector(),1.0),
         PlanePolicy("background",1,ResourceVector(),1.0)),
    ))


@pytest.fixture
def studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"worker.sqlite") as lib:
        almanacs=DragonAlmanacs(lib)
        atlas=DragonTechnicalSources(almanacs)
        epoch=int(datetime.fromisoformat(T0.replace("Z","+00:00")).timestamp())
        atlas.import_catalog(OWNER,authorized=True,recorded_at=epoch)
        db=sqlite3.connect(":memory:")
        nest=DragonNestStore(db,signing_key=b"test-worker-nest-signing-key-12345678")
        nest.initialize(OWNER,("initial-reviewed-source",),
                        focus_tags=("gameboy",),adjacent_tags=("debugging",),
                        at=T0,authorized=True)
        nest.record_parent(OWNER,"initial-reviewed-source",
                           content_sha256="a"*64,at=T0,
                           reviewed=True,lawful=True,authorized=True)
        try:
            yield lib,nest,DragonNestSourceFeed(almanacs,atlas,nest)
        finally:
            db.close()


def worker(feed, with_global=True):
    resources=ledger() if with_global else None
    session=DragonResourceSession(global_resources=resources,tenant=OWNER)
    return DragonNestWorkerAdmission(feed,session),session,resources


def begin(dispatcher,**kwargs):
    args=dict(owner=OWNER,sample=hw(),at=T2,idle_since=T0,
              now_seconds=1000,authorized=True,trusted_worker=True,
              consented=True,article_consent=True,video_consent=False,
              updates_consent=False)
    args.update(kwargs)
    return dispatcher.begin(**args)


def chunk(dispatcher,ticket,**kwargs):
    args=dict(sample=hw(),at=T2,idle_since=T0,
              now_seconds=1000,authorized=True,trusted_worker=True,
              consented=True,article_consent=True,video_consent=False,
              updates_consent=False)
    args.update(kwargs)
    return dispatcher.authorize_chunk(ticket,**args)


def stop(dispatcher,ticket):
    dispatcher.stopped(ticket,authorized=True,trusted_worker=True,
                       worker_stopped=True)


def test_without_shared_global_ledger_no_worker_ticket(studio):
    _,nest,feed=studio
    admission,session,_=worker(feed,False)
    response=begin(admission)
    assert response.ticket is None and not response.admitted
    assert response.reason=="global_resource_denied"
    assert not admission.active
    assert not session._active
    assert nest.read(OWNER,authorized=True).children[0].level==0


def test_real_global_grant_requires_chunk_revalidation_and_ack(studio):
    lib,nest,feed=studio
    admission,session,resources=worker(feed)
    before=lib.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs").fetchone()[0]
    result=begin(admission)
    assert result.admitted and result.reason=="resource_granted"
    ticket=result.ticket
    assert isinstance(ticket,HatchlingWorkerTicket)
    assert ticket.resource_granted and not ticket.network_authorized
    assert not ticket.memory_promotion_authorized
    assert len(resources.active_grants())==1
    assert chunk(admission,ticket)
    assert lib.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs").fetchone()[0]==before
    with pytest.raises(PermissionError,match="stop"):
        admission.stopped(ticket,authorized=True,trusted_worker=True,
                          worker_stopped=False)
    assert len(resources.active_grants())==1
    stop(admission,ticket)
    assert resources.active_grants()==()
    assert not admission.active
    assert nest.read(OWNER,authorized=True).children[0].level==0


def test_foreground_preemption_and_consent_revoke_chunk(studio):
    _,_,feed=studio
    admission,session,resources=worker(feed)
    ticket=begin(admission).ticket
    assert ticket is not None
    assert not chunk(admission,ticket,consented=False)
    assert not chunk(admission,ticket,idle_since=T2)
    assert not chunk(admission,ticket,sample=hw(pressure=.99))
    # A foreground request marks lower-priority workers for checkpoint,
    # without pretending they already freed memory.
    session.dispatch((SessionTask("foreground","user",8*1024**2,1),),
                     hw(),now=1000)
    assert session.yield_requested(ticket.task_id)
    assert not chunk(admission,ticket)
    assert len(resources.active_grants())>=1
    stop(admission,ticket)
    assert resources.active_grants()==()


def test_expired_or_forged_tickets_fail_without_releasing_grant(studio):
    _,_,feed=studio
    admission,_,resources=worker(feed)
    ticket=begin(admission).ticket
    assert ticket is not None
    forged=replace(ticket,assignment_digest="f"*64)
    assert not chunk(admission,forged)
    assert not chunk(admission,ticket,at=T3,now_seconds=1061,
                     sample=hw(1061))
    assert len(resources.active_grants())==1
    with pytest.raises(ValueError,match="forged"):
        stop(admission,forged)
    stop(admission,ticket)
    assert resources.active_grants()==()


def test_policy_block_after_reservation_cancels_next_chunk(studio):
    lib,_,feed=studio
    admission,_,resources=worker(feed)
    ticket=begin(admission).ticket
    assert ticket is not None
    lib.db.execute("UPDATE dragon_almanac_jobs SET state='blocked' "
                   "WHERE owner=? AND source=?",(OWNER,ticket.source_id))
    assert not chunk(admission,ticket)
    stop(admission,ticket)
    assert resources.active_grants()==()


def test_no_admission_before_idle_or_trusted_worker(studio):
    _,_,feed=studio
    admission,_,resources=worker(feed)
    assert not begin(admission,idle_since=T2).admitted
    assert not begin(admission,consented=False).admitted
    assert not begin(admission,sample=hw(thermal=True)).admitted
    assert resources.active_grants()==()
    with pytest.raises(PermissionError):
        begin(admission,trusted_worker=False)
    with pytest.raises(PermissionError):
        begin(admission,owner="other-owner")


def test_invalid_budget_and_bounded_ticket_identity(studio):
    _,_,feed=studio
    admission,_,_=worker(feed)
    for inputs in ({"memory_bytes":1},{"memory_bytes":True},
                   {"io_tokens":0},{"max_active":25}):
        with pytest.raises(ValueError,match="bounded"):
            begin(admission,**inputs)
    with pytest.raises(ValueError,match="resource ticket"):
        HatchlingWorkerTicket(OWNER,"article","source-x","https://example.org/",
                              "hatchling:x","a"*64,T0,T0)
