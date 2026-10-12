"""Fail-closed durable Dragon source scheduling, recovery and article execution."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import sqlite3
from urllib.parse import urlsplit

import pytest

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_technical_source_atlas import (
    CATALOG, DragonTechnicalSources,
)
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.dragon_technical_source_operations import DragonSourceOperations
from skeleton.ai.game_builder.dragon_source_policy_renewal import DragonSourcePolicyRenewal
from skeleton.ai.game_builder.dragon_source_refresh_planner import DragonSourceRefreshPlanner
from skeleton.ai.game_builder.dragon_research_supervisor import DragonResearchSupervisor
from skeleton.ai.game_builder.dragon_technical_source_acquisition import (
    acquire_canonical_technical_article,
)
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.webcrawler.dragon_nest_worker_admission import DragonNestWorkerAdmission
from skeleton.ai.webcrawler.dragon_resource_session import (
    DragonResourceSession, HardwareSample,
)
from skeleton.ai.webcrawler.core import FetchResponse, extract_document
from skeleton.ai.webcrawler.http import SafeHttpFetcher
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourceScheduler, GlobalResourcePolicy, PlanePolicy, ResourceVector,
)

OWNER="durable-studio"
T0="2026-10-12T12:00:00Z"
T2="2026-10-12T12:15:00Z"
START=int(datetime.fromisoformat(T0.replace("Z","+00:00")).timestamp())
NOW=int(datetime.fromisoformat(T2.replace("Z","+00:00")).timestamp())


def moment(seconds):
    return datetime.fromtimestamp(seconds,timezone.utc).isoformat().replace("+00:00","Z")


def hardware(at=1000):
    return HardwareSample(512*1024**2,8,.1,.75,True,False,float(at))


def resources():
    return GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=2000,memory_mb=128,io_tokens=100),
        (PlanePolicy("interactive",2,ResourceVector(),1.0),
         PlanePolicy("background",1,ResourceVector(),1.0)),
    ))


def consent():
    return dict(consented=True,article_consent=True,
                video_consent=False,updates_consent=False)


@pytest.fixture
def lab(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"durable.sqlite") as db:
        a=DragonAlmanacs(db)
        atlas=DragonTechnicalSources(a)
        atlas.import_catalog(OWNER,authorized=True,recorded_at=START)
        seed=next(s for s in CATALOG if s["slug"]=="pandocs")
        url=seed["url"]
        sid="source-"+sha256(url.encode()).hexdigest()
        db.db.execute(
            "UPDATE dragon_almanac_jobs SET state='blocked' "
            "WHERE owner=? AND source<>?",(OWNER,sid)
        )
        worker=SequentialAlmanacWorker(a)
        policy=worker.claim(OWNER,now=START,authorized=True,trusted_worker=True)
        assert policy.source_id==sid and policy.stage=="policy"
        worker.finish(policy,now=START+1,output_digest="a"*64,
            evidence={"url":policy.url,"input_digest":policy.input_digest,
                      "output_digest":"a"*64,"robots_permitted":True,
                      "terms_permitted":True,"reference_use_permitted":True,
                      "ssrf_checked":True,"expires_at":START+3600},
            authorized=True,trusted_worker=True)
        nest_db=sqlite3.connect(":memory:")
        nest=DragonNestStore(nest_db,signing_key=b"durable-operations-nest-key-32bytes!")
        nest.initialize(OWNER,("parent-review",),
                        focus_tags=("gameboy",),adjacent_tags=("debugging",),
                        at=T0,authorized=True)
        nest.record_parent(OWNER,"parent-review",content_sha256="a"*64,
                           at=T0,authorized=True,reviewed=True,lawful=True)
        global_scheduler=resources()
        admission=DragonNestWorkerAdmission(
            DragonNestSourceFeed(a,atlas,nest),
            DragonResourceSession(global_resources=global_scheduler,tenant=OWNER),
        )
        captures=DragonSourceCaptures(a)
        ops=DragonSourceOperations(captures)
        try:
            yield db,a,atlas,admission,global_scheduler,captures,ops,sid,url
        finally:
            for ticket,_,_ in list(admission.active.values()):
                admission.stopped(ticket,authorized=True,trusted_worker=True,
                                  worker_stopped=True)
            nest_db.close()


def begin(lab,now=NOW):
    _,_,_,admission,_,_,_,sid,_=lab
    result=admission.begin(
        OWNER,sample=hardware(1000+now-NOW),at=moment(now),idle_since=T0,
        now_seconds=float(1000+now-NOW),
        authorized=True,trusted_worker=True,**consent())
    assert result.admitted and result.ticket is not None
    assert result.ticket.source_id==sid
    return result.ticket


def schedule(lab,ready=NOW):
    *_,ops,sid,url=lab
    return ops.schedule(OWNER,sid,now=START+2,ready_at=ready,
                        authorized=True,trusted_worker=True)


def attach(lab,ticket,now=NOW):
    admission=lab[3];ops=lab[6]
    return ops.attach(ticket,admission,now=now,authorized=True,
                      trusted_worker=True)


def stop(lab,ticket):
    lab[3].stopped(ticket,authorized=True,trusted_worker=True,
                   worker_stopped=True)


def saved_doc(lab,at=NOW+1):
    url=lab[8]
    text=("Gameboy memory registers and frame timing matter for games. "
          "The original source describes hardware implementation details.")
    doc=extract_document(FetchResponse(
        url,200,{"content-type":"text/plain"},text.encode(),float(at)),url)
    assert doc is not None
    return text,doc


def test_schedule_requires_canonical_policy_and_idempotently_persists(lab):
    db,a,atlas,adm,g,caps,ops,sid,url=lab
    first=schedule(lab)
    second=schedule(lab)
    assert first["status"]=="scheduled"
    assert second["status"]=="already_scheduled"
    assert first["event_digest"]==second["event_digest"]
    assert ops.inspect(OWNER,sid,authorized=True)["event_count"]==1
    assert ops.review_queue(OWNER,authorized=True)["items"]==[]
    with pytest.raises(PermissionError):
        ops.schedule(OWNER,sid,now=START+2,ready_at=NOW,
                     authorized=True,trusted_worker=False)
    with pytest.raises(ValueError,match="unregistered"):
        ops.inspect("foreign-owner",sid,authorized=True)


def test_global_ticket_attaches_to_persistent_fence_and_rechecks_chunks(lab):
    schedule(lab)
    ticket=begin(lab)
    lease=attach(lab,ticket)
    ops=lab[6]
    assert lease.source_id==ticket.source_id
    assert not lease.acquisition_authorized
    assert ops.authorize_chunk(ticket,lab[3],sample=hardware(),at=T2,
        idle_since=T0,now_seconds=1000,authorized=True,
        trusted_worker=True,**consent())
    assert not ops.authorize_chunk(ticket,lab[3],sample=hardware(),at=T2,
        idle_since=T2,now_seconds=1000,authorized=True,
        trusted_worker=True,**consent())
    assert not ops.authorize_chunk(ticket,lab[3],sample=hardware(),at=T2,
        idle_since=T0,now_seconds=1000,authorized=True,
        trusted_worker=True,**{**consent(),"consented":False})
    # A second controller object / process sees the exact durable state.
    other=DragonSourceOperations(lab[5])
    assert other.inspect(OWNER,ticket.source_id,authorized=True)["state"]=="leased"
    with pytest.raises(PermissionError,match="unresolved|active"):
        other.attach(ticket,lab[3],now=NOW+6,authorized=True,trusted_worker=True)
    stop(lab,ticket)
    released=ops.release(ticket,lab[3],now=NOW+1,capture_digest=None,
                         authorized=True,trusted_worker=True)
    assert released["state"]=="retry_wait"
    assert released["next_ready_at"]==NOW+31
    assert not ops.authorize_chunk(ticket,lab[3],sample=hardware(),at=T2,
        idle_since=T0,now_seconds=1000,authorized=True,
        trusted_worker=True,**consent())


def test_capture_to_durable_review_queue_without_memory_promotion(lab):
    schedule(lab)
    ticket=begin(lab)
    attach(lab,ticket)
    text,doc=saved_doc(lab)
    saved=lab[5].record(
        OWNER,ticket.source_id,doc,capture_id="durable-proof",
        observed_at=NOW+1,authorized=True,trusted_worker=True,
        reference_storage_permitted=True,response_body_bytes=len(text))
    stop(lab,ticket)
    end=lab[6].release(
        ticket,lab[3],now=NOW+2,
        capture_digest=saved["capture_digest"],
        authorized=True,trusted_worker=True)
    assert end["state"]=="completed" and end["review_required"]
    queue=lab[6].review_queue(OWNER,authorized=True)
    assert len(queue["items"])==1
    assert queue["items"][0]["capture_digest"]==saved["capture_digest"]
    assert queue["items"][0]["independent_review_approved"] is False
    assert queue["model_training_authorized"] is False
    assert lab[0]._rows(OWNER)==[]
    with pytest.raises(ValueError,match="already|completed|queued"):
        lab[6].schedule(OWNER,ticket.source_id,now=NOW+4,
            ready_at=NOW+4,authorized=True,trusted_worker=True)


def test_replay_and_failed_capture_attestation_refused(lab):
    schedule(lab)
    ticket=begin(lab)
    attach(lab,ticket)
    stop(lab,ticket)
    with pytest.raises(ValueError,match="matching captured content"):
        lab[6].release(
            ticket,lab[3],now=NOW+2,capture_digest="a"*64,
            authorized=True,trusted_worker=True)
    end=lab[6].release(
        ticket,lab[3],now=NOW+2,capture_digest=None,
        authorized=True,trusted_worker=True)
    assert end["state"]=="retry_wait"
    with pytest.raises(ValueError,match="already released|missing"):
        lab[6].release(
            ticket,lab[3],now=NOW+3,capture_digest=None,
            authorized=True,trusted_worker=True)


def test_crash_expiry_quarantines_without_faking_global_stop(lab):
    schedule(lab)
    ticket=begin(lab)
    attach(lab,ticket)
    ops=lab[6]
    recovered=ops.quarantine_expired(
        OWNER,now=NOW+61,authorized=True,trusted_supervisor=True)
    assert len(recovered["quarantined"])==1
    assert recovered["resources_released"]==0
    assert lab[4].active_grants()
    assert ops.inspect(OWNER,ticket.source_id,authorized=True)["state"]=="quarantined"
    assert not ops.authorize_chunk(ticket,lab[3],sample=hardware(1061),
        at=moment(NOW+61),idle_since=T0,now_seconds=1061,
        authorized=True,trusted_worker=True,**consent())
    with pytest.raises(PermissionError,match="process-stop"):
        ops.confirm_recovered(OWNER,ticket.source_id,now=NOW+62,
            external_stop_receipt="f"*64,authorized=True,
            trusted_supervisor=True,worker_stopped=False,
            resources_reconciled=True)
    stop(lab,ticket)
    proof=ops.confirm_recovered(OWNER,ticket.source_id,now=NOW+62,
        external_stop_receipt="f"*64,authorized=True,
        trusted_supervisor=True,worker_stopped=True,
        resources_reconciled=True)
    assert proof["status"]=="ready_for_new_policy_review"
    res=ops.schedule(OWNER,ticket.source_id,now=NOW+63,
                     ready_at=NOW+63,authorized=True,trusted_worker=True)
    assert res["status"]=="scheduled"


def test_corrupt_event_or_corrupt_head_fails_closed(lab):
    schedule(lab)
    db,a,atlas,adm,g,caps,ops,sid,url=lab
    db.db.execute(
        "UPDATE dragon_source_ops_events_v1 SET body='{}' "
        "WHERE owner=? AND source=?",(OWNER,sid))
    with pytest.raises(ValueError,match="integrity"):
        ops.inspect(OWNER,sid,authorized=True)
    db.db.execute("DELETE FROM dragon_source_ops_events_v1 "
                  "WHERE owner=? AND source=?",(OWNER,sid))
    with pytest.raises(ValueError,match="head"):
        ops.inspect(OWNER,sid,authorized=True)


def test_real_article_worker_checks_durable_gate_and_releases_after_http(lab):
    schedule(lab)
    ticket=begin(lab)
    attach(lab,ticket)
    host=urlsplit(ticket.source_url).hostname
    fetcher=SafeHttpFetcher(allowed_hosts=frozenset({host}),
                            bind_dns_to_socket=True)
    network=[]
    def local_transport(url,*,user_agent,max_bytes,extra_headers=None):
        network.append(url)
        body=(b"User-agent: *\nAllow: /\n" if url.endswith("robots.txt")
              else b"Gameboy hardware memory and frame timing are documented. "
                   b"An original game implementation requires verified hardware constraints.")
        return FetchResponse(url,200,{"content-type":"text/plain"},body,float(NOW))
    fetcher.fetch_once=local_transport
    result=acquire_canonical_technical_article(
        lab[3],lab[5],ticket,fetcher=fetcher,
        sample_provider=hardware,
        consent_provider=consent,
        idle_since_provider=lambda:T0,at_provider=lambda:T2,
        clock=lambda:1000.0,sleep=lambda delay:None,
        capture_id="single-runtime-fetch",
        authorized=True,trusted_worker=True,
        reference_storage_permitted=True,operations=lab[6])
    assert result.captured
    assert len(network)==2 and any(x.endswith("/robots.txt") for x in network)
    assert lab[4].active_grants()==()
    assert lab[6].inspect(OWNER,ticket.source_id,authorized=True)["state"]=="completed"
    assert len(lab[6].review_queue(OWNER,authorized=True)["items"])==1


def test_worker_permission_failure_stops_and_backoffs_durable_lease(lab):
    schedule(lab)
    ticket=begin(lab)
    attach(lab,ticket)
    host=urlsplit(ticket.source_url).hostname
    fetcher=SafeHttpFetcher(allowed_hosts=frozenset({host}),bind_dns_to_socket=True)
    received=[]
    def local_transport(url,*,user_agent,max_bytes,extra_headers=None):
        received.append(url)
        return FetchResponse(url,200,{"content-type":"text/plain"},
                             b"User-agent: *\nAllow: /\n",float(NOW))
    fetcher.fetch_once=local_transport
    count=0
    def revoking():
        nonlocal count
        count+=1
        return consent() if count==1 else {**consent(),"consented":False}
    result=acquire_canonical_technical_article(
        lab[3],lab[5],ticket,fetcher=fetcher,
        sample_provider=hardware,
        consent_provider=revoking,
        idle_since_provider=lambda:T0,at_provider=lambda:T2,
        clock=lambda:1000.0,sleep=lambda delay:None,
        capture_id="cancelled-runtime-fetch",
        authorized=True,trusted_worker=True,
        reference_storage_permitted=True,operations=lab[6])
    assert not result.captured
    assert len(received)==1
    assert lab[4].active_grants()==()
    assert lab[6].inspect(OWNER,ticket.source_id,authorized=True)["state"]=="retry_wait"
    assert lab[6].review_queue(OWNER,authorized=True)["items"]==[]



def test_supervisor_refuses_undurable_or_unauthorized_acquisition(lab):
    coordinator=DragonResearchSupervisor(lab[6],lab[3])
    assert coordinator.ready(OWNER,now=NOW,authorized=True)["count"]==0
    result=coordinator.reserve_next(
        OWNER,sample=hardware(),at=T2,idle_since=T0,now_seconds=1000,
        authorized=True,trusted_worker=True,consented=True,article_consent=True)
    assert not result.ticket and result.status=="no_policy_ready_source"
    assert lab[4].active_grants()==()
    with pytest.raises(PermissionError):
        coordinator.reserve_next(
            OWNER,sample=hardware(),at=T2,idle_since=T0,now_seconds=1000,
            authorized=True,trusted_worker=False,consented=True,article_consent=True)


def test_supervisor_routes_only_durable_ready_source_and_grants_real_slot(lab):
    schedule(lab)
    coordinator=DragonResearchSupervisor(lab[6],lab[3])
    ready=coordinator.ready(OWNER,now=NOW,authorized=True)
    assert ready["count"]==1 and ready["ready_sources"]==[lab[7]]
    assert ready["execution_authorized"] is False
    accepted=coordinator.reserve_next(
        OWNER,sample=hardware(),at=T2,idle_since=T0,now_seconds=1000,
        authorized=True,trusted_worker=True,consented=True,article_consent=True)
    assert accepted.status=="durably_fenced_resource_granted"
    assert accepted.ticket and accepted.lease
    assert accepted.ticket.source_id==lab[7]
    assert accepted.lease.ticket_digest and not accepted.lease.acquisition_authorized
    assert len(lab[4].active_grants())==1
    assert coordinator.ready(OWNER,now=NOW+1,authorized=True)["count"]==0
    assert lab[6].inspect(OWNER,lab[7],authorized=True)["state"]=="leased"
    stop(lab,accepted.ticket)
    lab[6].release(accepted.ticket,lab[3],now=NOW+1,capture_digest=None,
                   authorized=True,trusted_worker=True)
    assert lab[4].active_grants()==()


def test_supervisor_foreground_consent_and_hardware_gate_do_not_scan_queue(lab):
    schedule(lab)
    coordinator=DragonResearchSupervisor(lab[6],lab[3])
    for overrides in (
        {"consented":False},
        {"article_consent":False},
        {"idle_since":T2},
        {"sample":HardwareSample(512*1024**2,8,.99,.75,True,False,1000.)},
    ):
        kwargs=dict(owner=OWNER,sample=hardware(),at=T2,idle_since=T0,
            now_seconds=1000,authorized=True,trusted_worker=True,
            consented=True,article_consent=True)
        kwargs.update(overrides)
        denied=coordinator.reserve_next(**kwargs)
        assert denied.ticket is None and denied.lease is None
        assert lab[4].active_grants()==()
    assert lab[6].inspect(OWNER,lab[7],authorized=True)["state"]=="scheduled"


def test_supervisor_rejects_backoff_or_expired_policy(lab):
    schedule(lab)
    coordinator=DragonResearchSupervisor(lab[6],lab[3])
    # Explicit ready time controls the queue, even when an atlas recommendation exists.
    lab[0].db.execute("UPDATE dragon_source_ops_heads_v1 SET ready_at=? "
        "WHERE owner=? AND source=?",(NOW-1,OWNER,lab[7]))
    with pytest.raises(ValueError,match="head mismatch"):
        coordinator.ready(OWNER,now=NOW,authorized=True)
    # Corruption is a hard stop, never a fallback to scanning raw URLs.


def test_supervisor_releases_unused_global_grant_on_durable_attach_race(lab):
    schedule(lab)
    coordinator=DragonResearchSupervisor(lab[6],lab[3])
    old=lab[6].attach
    def lost_race(*args,**kwargs):
        raise PermissionError("host delay changed in another process")
    lab[6].attach=lost_race
    try:
        denied=coordinator.reserve_next(
            OWNER,sample=hardware(),at=T2,idle_since=T0,now_seconds=1000,
            authorized=True,trusted_worker=True,consented=True,
            article_consent=True)
    finally:
        lab[6].attach=old
    assert denied.status=="durable_lease_raced_or_policy_changed"
    assert denied.ticket is None and denied.lease is None
    assert lab[4].active_grants()==()
    assert not lab[3].active
    assert lab[6].inspect(OWNER,lab[7],authorized=True)["state"]=="scheduled"


def test_supervisor_does_not_dispatch_into_crashed_leases(lab):
    schedule(lab)
    coordinator=DragonResearchSupervisor(lab[6],lab[3])
    reservation=coordinator.reserve_next(
        OWNER,sample=hardware(),at=T2,idle_since=T0,now_seconds=1000,
        authorized=True,trusted_worker=True,consented=True,
        article_consent=True)
    assert reservation.ticket
    quarantined=lab[6].quarantine_expired(OWNER,now=NOW+61,
        authorized=True,trusted_supervisor=True)
    assert len(quarantined["quarantined"])==1
    assert coordinator.ready(OWNER,now=NOW+62,authorized=True)["ready_sources"]==[]
    # Worker and global grant are still tracked until explicit stop.
    assert lab[4].active_grants()
    stop(lab,reservation.ticket)
    lab[6].confirm_recovered(OWNER,lab[7],now=NOW+62,
        external_stop_receipt="a"*64,authorized=True,
        trusted_supervisor=True,worker_stopped=True,
        resources_reconciled=True)
    lab[6].schedule(OWNER,lab[7],now=NOW+63,ready_at=NOW+65,
                    authorized=True,trusted_worker=True)
    assert coordinator.ready(OWNER,now=NOW+64,authorized=True)["ready_sources"]==[]
    assert coordinator.ready(OWNER,now=NOW+65,authorized=True)["ready_sources"]==[lab[7]]



def _robots_policy_worker(lab, *, crawl_delay):
    """Run existing socket-bound crawler against a deterministic local fixture."""
    schedule(lab)
    controller=DragonResearchSupervisor(lab[6],lab[3])
    reserved=controller.reserve_next(
        OWNER,sample=hardware(),at=T2,idle_since=T0,now_seconds=1000,
        authorized=True,trusted_worker=True,consented=True,article_consent=True)
    assert reserved.ticket is not None and reserved.lease is not None
    ticket=reserved.ticket
    host=urlsplit(ticket.source_url).hostname
    fetcher=SafeHttpFetcher(allowed_hosts=frozenset({host}),
                            bind_dns_to_socket=True)
    requested=[];slept=[]
    def fixture(url, *, user_agent, max_bytes, extra_headers=None):
        requested.append(url)
        if not url.endswith("/robots.txt"):
            raise AssertionError("long-delay policy unexpectedly fetched page")
        body=("User-agent: *\nCrawl-delay: "+str(crawl_delay)+
              "\nAllow: /\n").encode()
        return FetchResponse(url,200,{"content-type":"text/plain"},
                             body,float(NOW))
    fetcher.fetch_once=fixture
    result=acquire_canonical_technical_article(
        lab[3],lab[5],ticket,fetcher=fetcher,
        sample_provider=hardware,consent_provider=consent,
        idle_since_provider=lambda:T0,at_provider=lambda:T2,
        clock=lambda:1000.0,
        sleep=lambda seconds:slept.append(seconds),
        capture_id="robots-cooldown-policy-fixture",
        authorized=True,trusted_worker=True,reference_storage_permitted=True,
        operations=lab[6])
    assert len(requested)==1 and requested[0].endswith("/robots.txt")
    assert slept==[]
    assert lab[4].active_grants()==()
    assert not lab[3].active
    return result,lab[6].inspect(OWNER,lab[7],authorized=True)


def test_long_robots_delay_persists_ready_time_without_holding_worker(lab):
    result,state=_robots_policy_worker(lab,crawl_delay=180)
    assert result.captured is False
    assert result.reason=="deferred_for_robots_crawl_delay"
    assert result.retry_after_seconds==180
    assert not result.source_policy_hold
    assert state["state"]=="retry_wait"
    assert state["next_ready_at"]==NOW+180
    peer=DragonSourceOperations(lab[5])
    assert peer.ready_candidates(OWNER,now=NOW+179,authorized=True)==()
    assert peer.ready_candidates(OWNER,now=NOW+180,authorized=True)==(lab[7],)
    cooldown=lab[0].db.execute(
        "SELECT next_at FROM dragon_source_host_cooldown_v1 WHERE host=?",
        (urlsplit(lab[8]).hostname,)).fetchone()
    assert cooldown==(NOW+180,)
    assert lab[5].history(OWNER,lab[7],authorized=True)==()


def test_multiday_robots_delay_waits_without_synchronous_sleep(lab):
    result,state=_robots_policy_worker(lab,crawl_delay=172800)
    assert result.retry_after_seconds==172800
    assert state["next_ready_at"]==NOW+172800
    assert lab[6].ready_candidates(
        OWNER,now=NOW+86400,authorized=True)==()
    # The original policy expires before the next allowed attempt.
    # A fresh policy receipt must be granted separately before resuming.


def test_extreme_robots_delay_requires_manual_policy_hold(lab):
    result,state=_robots_policy_worker(lab,crawl_delay=700000)
    assert result.reason=="robots_delay_exceeds_week_manual_review"
    assert result.source_policy_hold
    assert result.retry_after_seconds is None
    assert state["state"]=="policy_hold"
    assert lab[6].ready_candidates(
        OWNER,now=NOW+700000,authorized=True)==()
    assert lab[0].db.execute(
        "SELECT next_at FROM dragon_source_host_cooldown_v1 WHERE host=?",
        (urlsplit(lab[8]).hostname,)).fetchone()==(4102444800,)
    with pytest.raises(ValueError,match="already|active|completed"):
        lab[6].schedule(OWNER,lab[7],now=NOW+1,
                        ready_at=NOW+1,authorized=True,trusted_worker=True)


def test_forged_robots_delay_is_not_accepted_from_untrusted_release(lab):
    schedule(lab)
    ticket=begin(lab)
    attach(lab,ticket)
    stop(lab,ticket)
    with pytest.raises(ValueError,match="only uncaptured"):
        lab[6].release(ticket,lab[3],now=NOW+1,capture_digest=None,
                       deferred_seconds=600,deferred_reason="generic_retry",
                       authorized=True,trusted_worker=True)
    with pytest.raises(ValueError,match="unbounded robots"):
        lab[6].release(ticket,lab[3],now=NOW+1,capture_digest=None,
                       deferred_reason="robots_delay_exceeds_limit",
                       deferred_seconds=600,policy_hold=True,
                       authorized=True,trusted_worker=True)
    assert lab[6].inspect(OWNER,lab[7],authorized=True)["state"]=="leased"
    lab[6].release(ticket,lab[3],now=NOW+1,capture_digest=None,
                   authorized=True,trusted_worker=True)
    assert lab[6].inspect(OWNER,lab[7],authorized=True)["state"]=="retry_wait"



def test_expired_policy_is_retired_archived_and_freshly_reapproved(lab):
    schedule(lab)
    ops=lab[6]
    renew=DragonSourcePolicyRenewal(ops)
    now=START+3601
    sid=lab[7]
    initial=ops.inspect(OWNER,sid,authorized=True)["head_digest"]
    report=renew.request(
        OWNER,sid,now=now,expected_operations_digest=initial,
        reason="expired_policy",authorized=True,trusted_supervisor=True)
    assert report["status"]=="awaiting_new_independent_policy_review"
    assert not report["crawler_authorized"]
    assert ops.ready_candidates(OWNER,now=now,authorized=True)==()
    assert ops.inspect(OWNER,sid,authorized=True)["state"]=="policy_recheck"
    assert lab[0].db.execute(
        "SELECT stage,state FROM dragon_almanac_jobs WHERE owner=? AND source=?",
        (OWNER,sid)).fetchone()==(0,"pending")
    assert lab[0].db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_archived_steps "
        "WHERE owner=? AND source=?",(OWNER,sid)).fetchone()[0]==1
    pending=renew.pending(OWNER,authorized=True)
    assert len(pending["items"])==1
    assert pending["items"][0]["policy_review_required"]
    assert pending["items"][0]["renewal_digest"]==report["renewal_digest"]
    with pytest.raises(ValueError,match="stale|missing"):
        renew.rearm(OWNER,sid,now=now+1,
                    expected_renewal_digest="f"*64,
                    authorized=True,trusted_supervisor=True)
    with pytest.raises(PermissionError,match="independent"):
        renew.rearm(OWNER,sid,now=now+1,
                    expected_renewal_digest=report["renewal_digest"],
                    authorized=True,trusted_supervisor=True)
    worker=SequentialAlmanacWorker(lab[1])
    policy=worker.claim(OWNER,now=now+1,authorized=True,trusted_worker=True)
    assert policy.source_id==sid and policy.stage=="policy"
    worker.finish(
        policy,now=now+2,output_digest="b"*64,
        evidence={"url":policy.url,"input_digest":policy.input_digest,
                  "output_digest":"b"*64,"robots_permitted":True,
                  "terms_permitted":True,"reference_use_permitted":True,
                  "ssrf_checked":True,"expires_at":now+7200},
        authorized=True,trusted_worker=True)
    assert not renew.pending("other-owner",authorized=True)["items"]
    resumed=renew.rearm(
        OWNER,sid,now=now+3,expected_renewal_digest=report["renewal_digest"],
        authorized=True,trusted_supervisor=True)
    assert resumed["status"]=="scheduled_after_policy_revalidation"
    assert ops.ready_candidates(OWNER,now=now+3,authorized=True)==(sid,)
    assert not renew.pending(OWNER,authorized=True)["items"]
    assert not resumed["source_rights_granted_by_this_method"]
    with pytest.raises(ValueError,match="stale|missing"):
        renew.rearm(OWNER,sid,now=now+4,
                    expected_renewal_digest=report["renewal_digest"],
                    authorized=True,trusted_supervisor=True)


def test_expiry_renewal_rejects_nonexpired_cas_and_manual_hold(lab):
    schedule(lab)
    renew=DragonSourcePolicyRenewal(lab[6])
    head=lab[6].inspect(OWNER,lab[7],authorized=True)["head_digest"]
    with pytest.raises(PermissionError,match="expired"):
        renew.request(OWNER,lab[7],now=NOW,
            expected_operations_digest=head,reason="expired_policy",
            authorized=True,trusted_supervisor=True)
    with pytest.raises(ValueError,match="compare-and-swap"):
        renew.request(OWNER,lab[7],now=START+3601,
            expected_operations_digest="f"*64,reason="expired_policy",
            authorized=True,trusted_supervisor=True)
    ticket=begin(lab)
    attach(lab,ticket)
    stop(lab,ticket)
    lab[6].release(ticket,lab[3],now=NOW+1,capture_digest=None,
        deferred_reason="robots_delay_exceeds_limit",policy_hold=True,
        authorized=True,trusted_worker=True)
    held=lab[6].inspect(OWNER,lab[7],authorized=True)
    assert held["state"]=="policy_hold"
    with pytest.raises(PermissionError,match="manually held"):
        renew.request(OWNER,lab[7],now=START+3601,
            expected_operations_digest=held["head_digest"],
            reason="expired_policy",authorized=True,trusted_supervisor=True)


def test_refresh_planner_surfaces_permission_expiry_without_auto_approval(lab):
    schedule(lab)
    planner=DragonSourceRefreshPlanner(lab[6])
    before=planner.assess(OWNER,lab[7],now=NOW,authorized=True)
    assert before["reason"]=="no_refresh_transition_required"
    assert not before["rights_granted"] and not before["observed_remote_change"]
    after=planner.assess(OWNER,lab[7],now=START+3601,authorized=True)
    assert after["reason"]=="policy_expired_requires_recheck"
    assert after["operator_revalidation_required"]
    assert after["latest_capture_digest"] is None
    assert after["suggested_review_days"]==90
    assert after["editorial_next_review_at"] is None
    assert lab[6].inspect(OWNER,lab[7],authorized=True)["state"]=="scheduled"
    with pytest.raises(ValueError,match="unregistered"):
        planner.assess("unrelated",lab[7],now=START+3601,authorized=True)
