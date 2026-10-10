"""Deterministic, policy-bound crawler core.

The plane is deliberately transport-agnostic: callers provide a Fetcher so tests and
production transports share the same policy/frontier/provenance state machine.
Network transports MUST enforce the same destination policy on every redirect.
"""

from __future__ import annotations

import hashlib
import heapq
from email.utils import parsedate_to_datetime
import html
import ipaddress
import json
import posixpath
import re
import time
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Iterable, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_ALLOWED_SCHEMES = {"http", "https"}


def canonicalize_url(url: str, *, base: str | None = None) -> str:
    """Return stable HTTP(S) identity, removing fragments and common tracking noise."""
    raw = urljoin(base, url) if base else url
    p = urlsplit(raw.strip())
    scheme = p.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES or not p.hostname:
        raise ValueError("only absolute http(s) URLs are crawlable")
    host = p.hostname.encode("idna").decode("ascii").lower()
    port = p.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    trailing = path.endswith("/")
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path
    if trailing and path != "/":
        path += "/"
    pairs = [
        (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS
        and not any(k.lower().startswith(prefix) for prefix in _TRACKING_PREFIXES)
    ]
    query = urlencode(sorted(pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def destination_allowed(host_or_ip: str) -> bool:
    """Fail closed for literal non-public destinations; DNS transports must recheck IPs."""
    try:
        ip = ipaddress.ip_address(host_or_ip.strip("[]"))
    except ValueError:
        return host_or_ip.lower() not in {"localhost", "localhost.localdomain"}
    return bool(ip.is_global)


@dataclass(frozen=True)
class CrawlPolicy:
    user_agent: str = "SkeletonAI-Crawler/1.0"
    max_depth: int = 4
    max_redirects: int = 5
    max_response_bytes: int = 4_000_000
    min_host_delay_seconds: float = 1.0
    max_retries: int = 3
    retry_base_seconds: float = 2.0
    max_retry_delay_seconds: float = 300.0
    max_links_per_document: int = 500
    max_url_length: int = 4096
    max_query_pairs: int = 32
    max_path_segments: int = 64
    robots_ttl_seconds: float = 86_400.0
    retry_statuses: tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504)
    allowed_content_types: tuple[str, ...] = (
        "text/html", "text/plain", "application/xhtml+xml",
    )
    allowed_hosts: frozenset[str] | None = None

    def admits(self, url: str) -> bool:
        try:
            p = urlsplit(canonicalize_url(url))
        except (ValueError, UnicodeError):
            return False
        if len(url) > self.max_url_length:
            return False
        if len(parse_qsl(p.query, keep_blank_values=True)) > self.max_query_pairs:
            return False
        if len([x for x in p.path.split("/") if x]) > self.max_path_segments:
            return False
        if not destination_allowed(p.hostname or ""):
            return False
        if self.allowed_hosts is not None and (p.hostname or "").lower() not in self.allowed_hosts:
            return False
        return True


@dataclass
class CrawlBudget:
    max_requests: int = 1000
    max_bytes: int = 100_000_000
    max_documents: int = 500
    requests: int = 0
    bytes: int = 0
    documents: int = 0

    def can_request(self) -> bool:
        return self.requests < self.max_requests and self.bytes < self.max_bytes

    def charge_response(self, byte_count: int, *, accepted: bool) -> None:
        self.requests += 1
        self.bytes += max(0, byte_count)
        if accepted:
            self.documents += 1

    @property
    def exhausted(self) -> bool:
        return (
            self.requests >= self.max_requests
            or self.bytes >= self.max_bytes
            or self.documents >= self.max_documents
        )


@dataclass(order=True)
class FrontierItem:
    ready_at: float
    priority: float
    sequence: int
    url: str = field(compare=False)
    depth: int = field(compare=False, default=0)
    parent_url: str | None = field(compare=False, default=None)
    attempts: int = field(compare=False, default=0)


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    fetched_at: float


class Fetcher(Protocol):
    def fetch(self, url: str, *, user_agent: str, max_bytes: int) -> FetchResponse: ...


@dataclass(frozen=True)
class CrawlDocument:
    canonical_url: str
    fetched_url: str
    title: str
    text: str
    content_type: str
    content_hash: str
    fetched_at: float
    source_score: float
    provenance: Mapping[str, object]
    links: tuple[str, ...]

    def retrieval_record(self) -> dict[str, object]:
        return {
            "id": self.content_hash,
            "text": self.text,
            "metadata": {
                "url": self.canonical_url,
                "title": self.title,
                "content_type": self.content_type,
                "source_score": self.source_score,
                "provenance": dict(self.provenance),
            },
        }


class _Extractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "canvas", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.text: list[str] = []
        self.links: list[str] = []
        self.title: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "a" and not self.skip:
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.text.append(cleaned)
            if self.in_title:
                self.title.append(cleaned)


def _source_score(url: str, text: str, status: int) -> float:
    p = urlsplit(url)
    score = 0.35
    if p.scheme == "https":
        score += 0.15
    if status == 200:
        score += 0.15
    if len(text) >= 500:
        score += 0.15
    if p.path.lower().endswith((".pdf", ".zip", ".exe")):
        score -= 0.25
    return max(0.0, min(1.0, score))


def extract_document(response: FetchResponse, canonical_url: str) -> CrawlDocument | None:
    ctype = response.headers.get("content-type", "text/plain").split(";", 1)[0].strip().lower()
    charset = "utf-8"
    match = re.search(r"charset=([^;\s]+)", response.headers.get("content-type", ""), re.I)
    if match:
        charset = match.group(1).strip('"\'')
    raw = response.body.decode(charset, errors="replace")
    title = ""
    links: list[str] = []
    if ctype in {"text/html", "application/xhtml+xml"}:
        parser = _Extractor()
        parser.feed(raw)
        text = " ".join(parser.text)
        title = " ".join(parser.title)
        links = parser.links
    elif ctype == "text/plain":
        text = raw
    else:
        return None
    text = html.unescape(" ".join(text.split())).strip()
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    normalized_links: list[str] = []
    for link in links:
        try:
            normalized_links.append(canonicalize_url(link, base=canonical_url))
        except (ValueError, UnicodeError):
            continue
    provenance = {
        "schema": "skeleton.ai.crawl.provenance.v1",
        "canonical_url": canonical_url,
        "fetched_url": response.url,
        "fetched_at": response.fetched_at,
        "status": response.status,
        "content_hash": digest,
    }
    return CrawlDocument(
        canonical_url=canonical_url,
        fetched_url=response.url,
        title=title[:1000],
        text=text,
        content_type=ctype,
        content_hash=digest,
        fetched_at=response.fetched_at,
        source_score=_source_score(canonical_url, text, response.status),
        provenance=provenance,
        links=tuple(dict.fromkeys(normalized_links)),
    )


class InMemoryCrawlStore:
    """Reference storage contract; durable stores can implement the same methods."""

    def __init__(self) -> None:
        self.documents: dict[str, CrawlDocument] = {}
        self.url_to_hash: dict[str, str] = {}
        self.checkpoints: dict[str, str] = {}

    def has_url(self, url: str) -> bool:
        return url in self.url_to_hash

    def has_content(self, digest: str) -> bool:
        return digest in self.documents

    def put(self, doc: CrawlDocument) -> bool:
        duplicate = doc.content_hash in self.documents
        self.url_to_hash[doc.canonical_url] = doc.content_hash
        if not duplicate:
            self.documents[doc.content_hash] = doc
        return not duplicate

    def save_checkpoint(self, key: str, state: Mapping[str, object]) -> None:
        self.checkpoints[key] = json.dumps(state, sort_keys=True, separators=(",", ":"))

    def load_checkpoint(self, key: str) -> dict[str, object] | None:
        raw = self.checkpoints.get(key)
        return json.loads(raw) if raw else None


class RobotsCache:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._meta: dict[str, dict[str, object]] = {}

    def install(self, origin: str, robots_text: str, *, fetched_at: float = 0.0, etag: str | None = None, last_modified: str | None = None) -> None:
        parser = RobotFileParser()
        parser.set_url(origin.rstrip("/") + "/robots.txt")
        parser.parse(robots_text.splitlines())
        self._parsers[origin] = parser
        self._meta[origin] = {"fetched_at": fetched_at, "etag": etag, "last_modified": last_modified}

    def known(self, url: str) -> bool:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}" in self._parsers

    def fresh(self, url: str, *, now: float, ttl: float) -> bool:
        p=urlsplit(url);meta=self._meta.get(f"{p.scheme}://{p.netloc}")
        return bool(meta and now-float(meta["fetched_at"]) < ttl)

    def validators(self, url: str) -> dict[str, str]:
        p=urlsplit(url);meta=self._meta.get(f"{p.scheme}://{p.netloc}") or {};out={}
        if meta.get("etag"):out["If-None-Match"]=str(meta["etag"])
        if meta.get("last_modified"):out["If-Modified-Since"]=str(meta["last_modified"])
        return out

    def touch(self,url: str, *, fetched_at: float) -> None:
        p=urlsplit(url);origin=f"{p.scheme}://{p.netloc}"
        if origin in self._meta:self._meta[origin]["fetched_at"]=fetched_at

    def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        parser = self._parsers.get(origin)
        # Fail closed until robots policy has explicitly been loaded.
        return parser is not None and parser.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        p = urlsplit(url)
        parser = self._parsers.get(f"{p.scheme}://{p.netloc}")
        return parser.crawl_delay(self.user_agent) if parser else None


class CrawlEngine:
    """Bounded deterministic scheduler with retries, dedupe and resumable state."""

    def __init__(
        self,
        fetcher: Fetcher,
        *,
        policy: CrawlPolicy | None = None,
        budget: CrawlBudget | None = None,
        store: InMemoryCrawlStore | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.policy = policy or CrawlPolicy()
        self.budget = budget or CrawlBudget()
        self.store = store or InMemoryCrawlStore()
        self.robots = RobotsCache(self.policy.user_agent)
        self._frontier: list[FrontierItem] = []
        self._queued: set[str] = set()
        self._seen: set[str] = set()
        self._host_ready: dict[str, float] = {}
        self._seq = 0

    def install_robots(self, origin: str, robots_text: str) -> None:
        self.robots.install(origin, robots_text)

    def enqueue(
        self, url: str, *, depth: int = 0, parent_url: str | None = None,
        priority: float = 0.0, ready_at: float = 0.0,
    ) -> bool:
        try:
            url = canonicalize_url(url, base=parent_url)
        except (ValueError, UnicodeError):
            return False
        if depth > self.policy.max_depth or not self.policy.admits(url):
            return False
        if url in self._queued or url in self._seen or self.store.has_url(url):
            return False
        self._seq += 1
        # heapq is min-first; negate caller priority so larger means sooner.
        heapq.heappush(self._frontier, FrontierItem(ready_at, -priority, self._seq, url, depth, parent_url))
        self._queued.add(url)
        return True

    def _next(self, now: float) -> FrontierItem | None:
        """Select the best ready item without one delayed host blocking all others."""
        blocked: list[FrontierItem] = []
        selected = None
        while self._frontier:
            item = heapq.heappop(self._frontier)
            host = urlsplit(item.url).hostname or ""
            ready = max(item.ready_at, self._host_ready.get(host, 0.0))
            if ready <= now:
                selected = item
                break
            blocked.append(item)
        for item in blocked:
            heapq.heappush(self._frontier, item)
        if selected is not None:
            self._queued.discard(selected.url)
        return selected

    def _retry(self, item: FrontierItem, *, now: float, delay: float | None = None) -> None:
        if item.attempts >= self.policy.max_retries:
            return
        self._seen.discard(item.url)
        fallback = self.policy.retry_base_seconds * (2 ** item.attempts)
        retry = min(self.policy.max_retry_delay_seconds, max(0.0, fallback if delay is None else delay))
        self._seq += 1
        heapq.heappush(self._frontier, FrontierItem(
            now + retry, item.priority, self._seq, item.url,
            item.depth, item.parent_url, item.attempts + 1,
        ))
        self._queued.add(item.url)

    @staticmethod
    def _retry_after(headers: Mapping[str, str], *, now: float | None = None) -> float | None:
        raw = headers.get("retry-after")
        if raw is None:
            return None
        try:
            return max(0.0, float(raw.strip()))
        except (ValueError, TypeError):
            try:
                target=parsedate_to_datetime(raw.strip()).timestamp()
                return max(0.0,target-(time.time() if now is None else now))
            except (ValueError,TypeError,OverflowError):
                return None

    def load_robots(self, url: str, *, now: float | None = None) -> bool:
        """Load an origin's robots policy once, charging the crawl budget."""
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        at=time.time() if now is None else now
        if self.robots.known(url) and self.robots.fresh(url,now=at,ttl=self.policy.robots_ttl_seconds):
            return True
        if not self.budget.can_request():
            return False
        robots_url = origin + "/robots.txt"
        try:
            from .redirects import fetch_robots_with_policy
            response = fetch_robots_with_policy(self, robots_url, now=at, extra_headers=self.robots.validators(url))
        except Exception:
            return False
        body = response.body[:512_000]
        if response.status == 304 and self.robots.known(url):
            self.robots.touch(url,fetched_at=at)
            return True
        if response.status in {404, 410}:
            self.robots.install(origin, "",fetched_at=at,etag=response.headers.get("etag"),last_modified=response.headers.get("last-modified"))
            return True
        if response.status != 200:
            return False
        ctype = response.headers.get("content-type", "text/plain").split(";", 1)[0].lower()
        if ctype not in {"text/plain", "text/html"}:
            return False
        self.robots.install(origin, body.decode("utf-8", errors="replace"),fetched_at=at,etag=response.headers.get("etag"),last_modified=response.headers.get("last-modified"))
        return True

    def step(self, *, now: float | None = None) -> CrawlDocument | None:
        now = time.time() if now is None else now
        if self.budget.exhausted or not self.budget.can_request():
            return None
        item = self._next(now)
        if item is None:
            return None
        if item.url in self._seen:
            return None
        self._seen.add(item.url)
        if not self.robots.known(item.url) and not self.load_robots(item.url, now=now):
            self._seen.discard(item.url)
            if self.budget.can_request(): self._retry(item, now=now)
            return None
        if not self.budget.can_request():
            self._seen.discard(item.url)
            return None
        if not self.robots.allowed(item.url):
            return None
        # fetch_with_policy owns the per-hop host cooldown. Reserving the
        # first hop here would make fetch_with_policy reject this same request
        # as premature, even after the scheduled frontier/robots delay.
        try:
            from .redirects import fetch_with_policy
            response = fetch_with_policy(self, item.url, now=now)
        except Exception as exc:
            from .redirects import RedirectFetchError
            if isinstance(exc,RedirectFetchError) and exc.request_started:self.budget.requests += 1
            self._retry(item, now=now)
            return None

        body = response.body[: self.policy.max_response_bytes]
        if response.status in self.policy.retry_statuses:
            self._retry(item, now=now, delay=self._retry_after(response.headers,now=response.fetched_at))
            return None
        ctype = response.headers.get("content-type", "").split(";", 1)[0].lower()
        accepted_type = ctype in self.policy.allowed_content_types
        successful = 200 <= response.status < 300 and accepted_type
        doc = extract_document(
            FetchResponse(response.url, response.status, response.headers, body, response.fetched_at),
            item.url,
        ) if successful else None
        novel = bool(doc and not self.store.has_content(doc.content_hash))
        # Redirect/robots transport charges each actual HTTP hop in
        # fetch_with_policy. Counting the fallback fetcher again here would
        # double-charge the same page and exhaust budgets prematurely.
        if novel:
            self.budget.documents += 1
        if not doc:
            return None
        self.store.put(doc)
        if novel and item.depth < self.policy.max_depth and not self.budget.exhausted:
            for link in doc.links[: self.policy.max_links_per_document]:
                self.enqueue(link, depth=item.depth + 1, parent_url=item.url)
        return doc if novel else None

    def checkpoint(self, key: str = "default") -> None:
        state = {
            "schema": "skeleton.ai.crawl.checkpoint.v1",
            "frontier": [asdict(x) for x in sorted(self._frontier)],
            "queued": sorted(self._queued),
            "seen": sorted(self._seen),
            "host_ready": self._host_ready,
            "sequence": self._seq,
            "budget": asdict(self.budget),
        }
        self.store.save_checkpoint(key, state)

    def restore(self, key: str = "default") -> bool:
        state = self.store.load_checkpoint(key)
        if not state or state.get("schema") != "skeleton.ai.crawl.checkpoint.v1":
            return False
        items = [FrontierItem(**x) for x in state["frontier"]]
        urls = [item.url for item in items]
        if len(urls) != len(set(urls)):
            return False
        queued = set(state["queued"])
        if queued != set(urls):
            return False
        self._frontier = items
        heapq.heapify(self._frontier)
        self._queued = queued
        self._seen = set(state["seen"])
        self._host_ready = {str(k): float(v) for k, v in state["host_ready"].items()}
        self._seq = int(state["sequence"])
        for k, v in state["budget"].items():
            setattr(self.budget, k, v)
        return True

    def retrieval_batch(self) -> list[dict[str, object]]:
        return [
            doc.retrieval_record()
            for doc in sorted(self.store.documents.values(), key=lambda d: d.canonical_url)
        ]
