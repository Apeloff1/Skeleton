"""Offline transport tests of the REAL source-capture worker admission path."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import sqlite3
from urllib.parse import urlsplit

import pytest

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_technical_source_atlas import DragonTechnicalSources
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.dragon_technical_source_acquisition import (
    acquire_canonical_technical_article,
)
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.http import SafeHttpFetcher
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.webcrawler.dragon_nest_worker_admission import DragonNestWorkerAdmission
from skeleton.ai.webcrawler.dragon_resource_session import DragonResourceSession,HardwareSample
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourceScheduler, GlobalResourcePolicy, PlanePolicy, ResourceVector,
)

OWNER="studio-worker"
T0="2026-10-12T12:00:00Z"
T2="2026-10-12T12:15:00Z"
EPOCH=int(datetime.fromisoformat(T2.replace("Z","+00:00")).timestamp())


def telemetry():
    return HardwareSample(512*1024**2,8,.1,.75,True,False,1000.0)


def grants():
    return GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=2000,memory_mb=128,io_tokens=100),
        (PlanePolicy("interactive",2,ResourceVector(),1.0),
         PlanePolicy("background",1,ResourceVector(),1.0)),
    ))


def consents():
    return dict(consented=True,article_consent=True,
                video_consent=False,updates_consent=False)


@pytest.fixture
def studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"integration.sqlite") as library:
        almanacs=DragonAlmanacs(library)
        atlas=DragonTechnicalSources(almanacs)
        atlas.import_catalog(OWNER,authorized=True,
                             recorded_at=int(datetime.fromisoformat(
                                 T0.replace("Z","+00:00")).timestamp()))
        nest_db=sqlite3.connect(":memory:")
        nest=DragonNestStore(nest_db,signing_key=b"capture-worker-integration-signer-32!")
        nest.initialize(OWNER,("initial-parent",),
                        focus_tags=("gameboy",),adjacent_tags=("debugging",),
                        at=T0,authorized=True)
        nest.record_parent(OWNER,"initial-parent",content_sha256="a"*64,
                           at=T0,authorized=True,reviewed=True,lawful=True)
        scheduler=grants()
        admission=DragonNestWorkerAdmission(
            DragonNestSourceFeed(almanacs,atlas,nest),
            DragonResourceSession(global_resources=scheduler,tenant=OWNER),
        )
        response=admission.begin(
            OWNER,sample=telemetry(),at=T2,idle_since=T0,
            now_seconds=1000,authorized=True,trusted_worker=True,
            **consents()
        )
        assert response.admitted and response.ticket is not None
        ticket=response.ticket
        captures=DragonSourceCaptures(almanacs)
        try:
            yield library,almanacs,admission,scheduler,ticket,captures
        finally:
            if ticket.task_id in admission.active:
                admission.stopped(ticket,authorized=True,trusted_worker=True,
                                  worker_stopped=True)
            nest_db.close()


def grant_existing_policy(studio):
    library,almanacs,admission,scheduler,ticket,captures=studio
    library.db.execute(
        "UPDATE dragon_almanac_jobs SET state='blocked' "
        "WHERE owner=? AND source<>?",(OWNER,ticket.source_id)
    )
    claim=SequentialAlmanacWorker(almanacs).claim(
        OWNER,now=EPOCH-800,authorized=True,trusted_worker=True,ttl=120
    )
    assert claim.source_id==ticket.source_id and claim.stage=="policy"
    output="b"*64
    evidence={"url":claim.url,"input_digest":claim.input_digest,
              "output_digest":output,"robots_permitted":True,
              "terms_permitted":True,"reference_use_permitted":True,
              "ssrf_checked":True,"expires_at":EPOCH+100}
    SequentialAlmanacWorker(almanacs).finish(
        claim,now=EPOCH-799,output_digest=output,evidence=evidence,
        authorized=True,trusted_worker=True
    )


def execute(studio,*,permission=consents,fetcher=None):
    _,_,admission,_,ticket,captures=studio
    calls=[]
    if fetcher is None:
        host=urlsplit(ticket.source_url).hostname
        fetcher=SafeHttpFetcher(allowed_hosts=frozenset({host}),
                                bind_dns_to_socket=True)
        def offline_fetch(url,*,user_agent,max_bytes,extra_headers=None):
            calls.append(url)
            if url.endswith("/robots.txt"):
                body=b"User-agent: *\nAllow: /\n"
            else:
                body=(b"Gameboy hardware sprite buffers and memory registers "
                      b"are documented for original homebrew development. "
                      b"Frame timing and game engine memory layout require care.")
            return FetchResponse(url,200,{"content-type":"text/plain"},body,
                                 float(EPOCH))
        fetcher.fetch_once=offline_fetch
    result=acquire_canonical_technical_article(
        admission,captures,ticket,fetcher=fetcher,
        sample_provider=telemetry,consent_provider=permission,
        idle_since_provider=lambda:T0,at_provider=lambda:T2,
        clock=lambda:1000.0,sleep=lambda _:None,
        capture_id="real-worker-attempt-1",
        authorized=True,trusted_worker=True,
        reference_storage_permitted=True
    )
    return result,calls


def test_policy_absent_blocks_http_before_first_request_and_releases_global_grant(studio):
    _,_,admission,scheduler,ticket,captures=studio
    with pytest.raises(PermissionError,match="policy"):
        execute(studio)
    assert scheduler.active_grants()==()
    assert admission.active=={}
    assert captures.history(OWNER,ticket.source_id,authorized=True)==()


def test_robots_checked_fetch_is_staged_and_exactly_one_grant_released(studio):
    grant_existing_policy(studio)
    result,calls=execute(studio)
    _,_,admission,scheduler,ticket,captures=studio
    assert result.captured and result.reason=="captured_pending_independent_review"
    assert result.revision["change"]=="new"
    assert result.revision["independent_review_required"]
    assert len(calls)==2
    assert any(x.endswith("/robots.txt") for x in calls)
    assert ticket.source_url in calls
    assert scheduler.active_grants()==()
    assert not admission.active
    assert captures.review_packet(OWNER,ticket.source_id,
                                  authorized=True)["candidate_quotes"]


def test_consent_loss_after_robots_does_not_commit_or_retain_grant(studio):
    grant_existing_policy(studio)
    count=0
    def revoked():
        nonlocal count
        count+=1
        return consents() if count<2 else {
            **consents(),"consented":False
        }
    result,calls=execute(studio,permission=revoked)
    _,_,admission,scheduler,ticket,captures=studio
    assert not result.captured
    assert len(calls)<=1
    assert scheduler.active_grants()==()
    assert captures.history(OWNER,ticket.source_id,authorized=True)==()


def test_unbound_dns_denied_and_worker_grant_released(studio):
    _,_,admission,scheduler,ticket,captures=studio
    with pytest.raises(PermissionError,match="DNS-to-socket"):
        execute(studio,fetcher=SafeHttpFetcher(bind_dns_to_socket=False))
    assert scheduler.active_grants()==()
    assert not admission.active


def test_multi_host_transport_denied_and_grant_released(studio):
    _,_,admission,scheduler,ticket,captures=studio
    with pytest.raises(PermissionError,match="single trusted"):
        execute(studio,fetcher=SafeHttpFetcher(
            allowed_hosts=frozenset({urlsplit(ticket.source_url).hostname,
                                     "other.example.org"}),bind_dns_to_socket=True))
    assert scheduler.active_grants()==()
    assert not admission.active
