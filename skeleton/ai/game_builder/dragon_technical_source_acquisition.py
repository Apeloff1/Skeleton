"""One-source, globally resource-granted Dragon article acquisition.

This is real network-worker wiring, not a simulation. All HTTP requests use
socket-bound DNS and the existing robots-aware CrawlEngine. It requires an
already completed, still-current canonical policy receipt and a Dragon global
resource grant. A research ticket *alone* never approves network access.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable
from urllib.parse import urlsplit

from skeleton.ai.webcrawler.core import CrawlBudget, CrawlEngine, CrawlPolicy
from skeleton.ai.webcrawler.http import SafeHttpFetcher
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)
from .dragon_technical_source_captures import DragonSourceCaptures


@dataclass(frozen=True, slots=True)
class SourceAcquisitionResult:
    owner: str
    source_id: str
    captured: bool
    reason: str
    revision: dict | None
    requests_performed: int
    model_promotion_authorized: bool = False


def _epoch(value: str) -> int:
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone-aware worker observation required")
    return int(dt.timestamp())


class _AdmittedHTTP:
    """Check the live grant before *every* robots/page request."""

    def __init__(self, fetcher: SafeHttpFetcher, admission: DragonNestWorkerAdmission,
                 ticket: HatchlingWorkerTicket, *, sample_provider, consent_provider,
                 idle_since_provider, at_provider, clock):
        self.fetcher=fetcher
        self.admission=admission
        self.ticket=ticket
        self.sample_provider=sample_provider
        self.consent_provider=consent_provider
        self.idle_since_provider=idle_since_provider
        self.at_provider=at_provider
        self.clock=clock
        self.requests=0
        self.page_bytes=None

    def fetch_once(self,url,*,user_agent,max_bytes,extra_headers=None):
        if self.requests>=4:
            raise PermissionError("Dragon source request budget exceeded")
        flags=self.consent_provider()
        if not isinstance(flags,dict) or set(flags)!={
            "consented","article_consent","video_consent","updates_consent"
        }:
            raise PermissionError("live typed specialist consent required")
        if not self.admission.authorize_chunk(
            self.ticket, sample=self.sample_provider(),
            at=self.at_provider(), idle_since=self.idle_since_provider(),
            now_seconds=self.clock(), authorized=True,trusted_worker=True,
            **flags
        ):
            raise PermissionError("idle lease or research consent revoked")
        self.requests+=1
        response=self.fetcher.fetch_once(
            url,user_agent=user_agent,max_bytes=max_bytes,
            extra_headers=extra_headers
        )
        if url==self.ticket.source_url and response.status==200:
            self.page_bytes=len(response.body)
        return response


def acquire_canonical_technical_article(
    admission: DragonNestWorkerAdmission, captures: DragonSourceCaptures,
    ticket: HatchlingWorkerTicket, *,
    fetcher: SafeHttpFetcher,
    sample_provider: Callable[[],HardwareSample],
    consent_provider: Callable[[],dict],
    idle_since_provider: Callable[[],str],
    at_provider: Callable[[],str],
    clock: Callable[[],float],
    sleep: Callable[[float],None],
    capture_id: str,
    authorized: bool,
    trusted_worker: bool,
    reference_storage_permitted: bool,
) -> SourceAcquisitionResult:
    """Fetch and stage ONE editorial article, then acknowledge the worker stop.

    Caller must own the ticket and the worker; the finally block releases the
    resource reservation only after synchronous transport has stopped.
    Never invoke this function from a browser request.
    """
    if not isinstance(admission,DragonNestWorkerAdmission):
        raise TypeError("canonical Dragon worker admission required")
    if not isinstance(captures,DragonSourceCaptures):
        raise TypeError("canonical captured-source ledger required")
    if not isinstance(ticket,HatchlingWorkerTicket):
        raise TypeError("bounded specialist worker ticket required")
    if authorized is not True or trusted_worker is not True:
        raise PermissionError("trusted authenticated capture worker required")
    try:
        if reference_storage_permitted is not True:
            raise PermissionError("explicit reference text retention permission required")
        if ticket.lane!="article":
            raise PermissionError("video/update sources require dedicated media/revision workers")
        if captures.a is not admission.feed.almanacs:
            raise PermissionError("same authoritative source registry required")
        if (not isinstance(fetcher,SafeHttpFetcher)
            or fetcher.bind_dns_to_socket is not True):
            raise PermissionError("DNS-to-socket-bound transport required")
        if any(not callable(x) for x in (sample_provider,consent_provider,
                                         idle_since_provider,at_provider,clock,sleep)):
            raise ValueError("live, trusted telemetry and timing callbacks required")
        host=urlsplit(ticket.source_url).hostname
        if not host or fetcher.allowed_hosts!=frozenset({host}):
            raise PermissionError("single trusted source-host transport required")
        guarded=_AdmittedHTTP(fetcher,admission,ticket,
                             sample_provider=sample_provider,
                             consent_provider=consent_provider,
                             idle_since_provider=idle_since_provider,
                             at_provider=at_provider,clock=clock)
        requests=0
        now=_epoch(at_provider())
        # A URL in the catalog is not permission. Require a canonical policy
        # step completed by another worker, including current terms/robots.
        source,_=captures._source(ticket.owner,ticket.source_id)
        if source["url"]!=ticket.source_url:
            raise ValueError("source record changed after worker was admitted")
        captures._policy(ticket.owner,ticket.source_id,ticket.source_url,
                         observed_at=now)
        engine=CrawlEngine(
            guarded,
            policy=CrawlPolicy(
                allowed_hosts=frozenset({host}),max_depth=0,max_redirects=0,
                max_response_bytes=240_000,min_host_delay_seconds=1.0,
                max_retries=0,max_links_per_document=0,
            ),
            budget=CrawlBudget(max_requests=4,max_bytes=700_000,
                               max_documents=1),
        )
        if not engine.enqueue(ticket.source_url):
            return SourceAcquisitionResult(ticket.owner,ticket.source_id,False,
                                           "canonical_url_rejected",None,guarded.requests)
        if not engine.load_robots(ticket.source_url,now=float(now)):
            return SourceAcquisitionResult(ticket.owner,ticket.source_id,False,
                                           "robots_unavailable_or_disallowed",None,
                                           guarded.requests)
        delay=max(1.0,engine.robots.crawl_delay(ticket.source_url) or 0.0)
        if delay>5.0:
            return SourceAcquisitionResult(ticket.owner,ticket.source_id,False,
                                           "requires_external_delayed_worker",None,
                                           guarded.requests)
        sleep(delay)
        # Permission, task relevance, idle and global resource grants are
        # rechecked inside guarded.fetch_once for the actual page request.
        result=engine.step(now=max(clock(),float(now)+delay))
        if result is None:
            return SourceAcquisitionResult(ticket.owner,ticket.source_id,False,
                                           "no_captured_document",None,guarded.requests)
        if (result.canonical_url!=ticket.source_url
            or result.fetched_url!=ticket.source_url
            or sha256(result.text.encode("utf-8")).hexdigest()!=result.content_hash):
            raise ValueError("redirected or corrupt source capture")
        now=_epoch(at_provider())
        flags=consent_provider()
        if not isinstance(flags,dict) or flags.get("consented") is not True:
            raise PermissionError("consent lost before reference capture")
        if not admission.authorize_chunk(
            ticket,sample=sample_provider(),at=at_provider(),
            idle_since=idle_since_provider(),now_seconds=clock(),
            authorized=True,trusted_worker=True,**flags
        ):
            raise PermissionError("idle worker cancelled before capture commit")
        entry=captures.record(
            ticket.owner,ticket.source_id,result,capture_id=capture_id,
            observed_at=now,authorized=True,trusted_worker=True,
            reference_storage_permitted=True,
            response_body_bytes=guarded.page_bytes
        )
        return SourceAcquisitionResult(ticket.owner,ticket.source_id,True,
                                       "captured_pending_independent_review",
                                       entry,guarded.requests)
    finally:
        # Transport is synchronous: the worker has exited network calls here.
        # A preempt request alone never frees physical resources.
        admission.stopped(ticket,authorized=True,trusted_worker=True,
                          worker_stopped=True)
