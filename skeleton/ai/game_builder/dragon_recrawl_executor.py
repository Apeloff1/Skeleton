"""One-shot consented, resource-granted source recrawl using the real crawler.

Live network mode exclusively uses SocketBoundFetcher via SafeHttpFetcher,
which pins validated public DNS at socket connection time and does not follow
redirects outside CrawlEngine's per-hop policies. Nothing is admitted to
Almanac memory automatically: output is only a review candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import time
from typing import Callable
from urllib.parse import urlsplit

from skeleton.ai.webcrawler.core import (
    CrawlBudget, CrawlDocument, CrawlEngine, CrawlPolicy, canonicalize_url,
)
from skeleton.ai.webcrawler.http import SafeHttpFetcher
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample

from .dragon_recrawl_dispatch import DragonRecrawlDispatcher, RecrawlWorkerTicket
from .dragon_wisdom_pyramid import _id, _time


@dataclass(frozen=True, slots=True)
class RecrawlResearchCandidate:
    owner: str
    source_id: str
    parent_revision: str
    request_digest: str
    captured_content_hash: str
    source_url: str
    document: CrawlDocument
    source_review_required: bool = True
    memory_promotion_authorized: bool = False


class _GatedFetcher:
    def __init__(self, fetcher, dispatcher, ticket, sample_provider, clock):
        self.fetcher = fetcher
        self.dispatcher = dispatcher
        self.ticket = ticket
        self.sample_provider = sample_provider
        self.clock = clock
        self.requests = 0

    def fetch_once(self, url: str, *, user_agent: str, max_bytes: int,
                   extra_headers=None):
        at = int(self.clock())
        if not self.dispatcher.authorize_chunk(
            self.ticket, self.sample_provider(), now=at, authorized=True,
            trusted_worker=True, consent=True,
        ):
            raise PermissionError("recrawl lease/preemption/consent is no longer valid")
        if self.requests >= 5:
            raise ValueError("network request budget exhausted")
        self.requests += 1
        return self.fetcher.fetch_once(
            url, user_agent=user_agent, max_bytes=max_bytes,
            extra_headers=extra_headers,
        )


def run_admitted_recrawl(
    dispatcher: DragonRecrawlDispatcher, *, owner: str,
    sample_provider: Callable[[], HardwareSample],
    fetcher: SafeHttpFetcher, now: int,
    authorized: bool, trusted_worker: bool, consent: bool,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> RecrawlResearchCandidate | None:
    """Fetch robots and one canonical reviewed source, stop, then hand off.

    The caller must separately authenticate the operator and explicitly consent
    to this source acquisition; no public HTTP API exposes this call.
    The runtime invokes a separately verified independent review BEFORE importing
    any revised document, then uses the existing complete_recrawl operation.
    """
    if authorized is not True or trusted_worker is not True or consent is not True:
        raise PermissionError("explicit trusted and consented crawler work required")
    if not isinstance(dispatcher, DragonRecrawlDispatcher):
        raise TypeError("Dragon recrawl scheduler required")
    _id(owner); _time(now)
    if not callable(sample_provider) or not callable(clock) or not callable(sleep):
        raise ValueError("runtime worker callbacks required")
    if not isinstance(fetcher, SafeHttpFetcher) or fetcher.bind_dns_to_socket is not True:
        raise PermissionError("socket-bound public destination transport required")
    sample = sample_provider()
    ticket = dispatcher.begin(
        owner, sample, now=now, authorized=True,
        trusted_worker=True, consent=True, memory_bytes=8 * 1024**2,
        io_tokens=5,
    )
    if ticket is None:
        return None
    try:
        # Never obtain a URL from the browser, a search snippet or the
        # recrawl queue. The canonical source authority owns the URL.
        rows = dispatcher.pyramid.library._rows(owner)
        sources = [s for s in rows if s["source_id"] == ticket.source_id]
        if len(sources) != 1 or sources[0]["revision_digest"] != ticket.source_revision:
            raise ValueError("stale recrawl source or ambiguous source custody")
        url = sources[0]["source_url"]
        canonical = canonicalize_url(url)
        parts = urlsplit(url)
        if canonical != url or parts.scheme != "https" or parts.username or parts.password:
            raise PermissionError("recrawl requires exact canonical public HTTPS URL")
        host = parts.hostname or ""
        if fetcher.allowed_hosts is not None and host not in fetcher.allowed_hosts:
            raise PermissionError("canonical source host is not allowed")
        bounded_policy = CrawlPolicy(
            allowed_hosts=frozenset({host}), max_depth=0, max_redirects=1,
            max_response_bytes=400_000, min_host_delay_seconds=1.0,
            max_retries=0, max_links_per_document=0,
        )
        guarded = _GatedFetcher(fetcher, dispatcher, ticket,
                                sample_provider, clock)
        engine = CrawlEngine(guarded, policy=bounded_policy,
                             budget=CrawlBudget(max_requests=5,
                                                max_bytes=1_200_000,
                                                max_documents=1))
        if not engine.enqueue(url):
            raise ValueError("canonical URL rejected by crawler policy")
        if not engine.load_robots(url, now=float(now)):
            return None
        # The robots fetch and page fetch must observe host-delay rules.
        # Bound the synchronous wait; production should use an external
        # scheduled worker rather than holding open a user-facing request.
        delay = max(1.0, engine.robots.crawl_delay(url) or 0.0)
        if delay > 5.0:
            return None  # External scheduler must respect longer crawl delays.
        sleep(delay)
        if not dispatcher.authorize_chunk(
            ticket, sample_provider(), now=int(clock()), authorized=True,
            trusted_worker=True, consent=True,
        ):
            return None
        result = engine.step(now=max(float(clock()), float(now) + delay))
        if result is None or result.canonical_url != url:
            return None
        if sha256(result.text.encode("utf-8")).hexdigest() != result.content_hash:
            raise ValueError("crawler source digest does not verify")
        return RecrawlResearchCandidate(
            owner, ticket.source_id, ticket.source_revision,
            ticket.order_digest, result.content_hash, url, result,
        )
    finally:
        # Only after the synchronous transport has returned (or raised) may
        # a trusted worker truthfully confirm that its grant was released.
        dispatcher.stopped(ticket, authorized=True,
                           trusted_worker=True, worker_stopped=True)
        dispatcher.abandon(ticket, authorized=True, trusted_worker=True)
