"""Bounded foreground crawl operations under the existing crawler owner.

The application stores these snapshots in its existing Mongo authority. This
module neither opens a database nor starts a worker/scheduler. External content
is retained as unreviewed evidence, never as verified knowledge or training data.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .core import (
    CrawlDocument,
    CrawlEngine,
    CrawlPolicy,
    FetchResponse,
    RobotsCache,
    _source_score,
    canonicalize_url,
    extract_document,
)
from .dragon_mission_quality import rank_query_passages, scan_untrusted_instructions
from .http import SafeHttpFetcher
from .research import EvidenceObservation

SCHEMA = "skeleton.ai.dragon.crawl_run.v1"
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
MAX_TEXT_BYTES = 24000
MAX_FRONTIER = 512
_TERMINAL = {"completed", "cancelled", "budget_exhausted"}
_STATES = {"ready", "running", "paused", "failed", *_TERMINAL}
_REDIRECTS = {301, 302, 303, 307, 308}
_RETRY = {408, 425, 429, 500, 502, 503, 504}


class CrawlOperationError(ValueError):
    """Invalid admission, state, authority, or persisted crawl evidence."""


class _CheckpointInterrupted(CrawlOperationError):
    """A rejected checkpoint must never become a transport retry."""


def _json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def implementation_digest():
    root = Path(__file__).parent
    return _digest(
        {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "operations.py",
                "core.py",
                "http.py",
                "bound_http.py",
                "dns_binding.py",
                "research.py",
                "dragon_mission_quality.py",
            )
        }
    )


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise CrawlOperationError(f"invalid {name}")
    return value


def _number(value, low, high, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise CrawlOperationError(f"invalid {name}")
    return value


def _text(value, maximum, name, *, empty=False):
    if (
        not isinstance(value, str)
        or (not empty and not value.strip())
        or len(value.encode("utf-8")) > maximum
        or any(ord(c) < 32 and c not in "\n\t" for c in value)
    ):
        raise CrawlOperationError(f"invalid {name}")
    return value


def _url(value):
    value = canonicalize_url(_text(value, 4096, "URL"))
    p = urlsplit(value)
    if p.port is not None or p.hostname in {"localhost", "localhost.localdomain"}:
        raise CrawlOperationError("only default-port public URLs are admitted")
    return value


@dataclass(frozen=True)
class CrawlRequest:
    seed_urls: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    query: str = ""
    max_depth: int = 1
    max_requests: int = 24
    max_documents: int = 16
    max_response_bytes: int = 524288
    max_total_bytes: int = 8388608
    min_host_delay_seconds: float = 1.0

    def __post_init__(self):
        if not isinstance(self.seed_urls, (tuple, list)) or not 1 <= len(self.seed_urls) <= 16:
            raise CrawlOperationError("one to sixteen seed URLs are required")
        if not isinstance(self.allowed_hosts, (tuple, list)) or not 1 <= len(self.allowed_hosts) <= 16:
            raise CrawlOperationError("an explicit host allowlist is required")
        hosts = []
        for host in self.allowed_hosts:
            host = _text(host, 253, "allowed host").encode("idna").decode("ascii").lower()
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
                raise CrawlOperationError("invalid allowed host")
            hosts.append(host)
        seeds = tuple(dict.fromkeys(_url(url) for url in self.seed_urls))
        if any(urlsplit(url).hostname not in hosts for url in seeds):
            raise CrawlOperationError("seed host is outside allowlist")
        object.__setattr__(self, "seed_urls", seeds)
        object.__setattr__(self, "allowed_hosts", tuple(sorted(set(hosts))))
        _text(self.query, 1024, "query", empty=True)
        for name, low, high in (
            ("max_depth", 0, 3),
            ("max_requests", 1, 128),
            ("max_documents", 1, 64),
            ("max_response_bytes", 1024, 2097152),
            ("max_total_bytes", 1024, 33554432),
        ):
            _integer(getattr(self, name), low, high, name)
        _number(self.min_host_delay_seconds, 0.25, 30, "host delay")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise CrawlOperationError("unknown crawl request fields")
        try:
            return cls(**value)
        except TypeError as exc:
            raise CrawlOperationError("incomplete crawl request") from exc

    def as_dict(self):
        return json.loads(_json(asdict(self)))


class CrawlRun:
    """Single-writer state machine. Each step performs at most one HTTP request."""

    def __init__(self):
        self._state = {}
        self.fetcher = None

    @classmethod
    def create(cls, request, *, scope, consent, now=None, fetcher=None):
        at = time.time() if now is None else _number(now, 0, 1e12, "time")
        request = request if isinstance(request, CrawlRequest) else CrawlRequest.from_dict(request)
        scope = cls._scope(scope)
        consent = cls._consent(consent)
        if not at < consent["expires_at"] <= at + 86400:
            raise CrawlOperationError("capture consent must expire within twenty-four hours")
        binding = {
            "request": request.as_dict(),
            "request_digest": _digest(request.as_dict()),
            "code_digest": implementation_digest(),
            "scope": scope,
            "consent": consent,
        }
        run = cls()
        run._state = {
            "schema_version": SCHEMA,
            "binding": binding,
            "run_id": _digest(binding),
            "state": "ready",
            "sequence": 0,
            "usage": {"requests": 0, "bytes": 0, "reserved_bytes": 0, "documents": 0, "failures": 0},
            "frontier": [],
            "seen": [],
            "host_ready": {},
            "robots": {},
            "sources": {},
            "events": [],
            "stop_reason": None,
            "pending_dispatch": None,
        }
        run._configure(fetcher)
        for url in request.seed_urls:
            run._enqueue(url, depth=0, parent_url=None)
        return run

    @staticmethod
    def _scope(value):
        if not isinstance(value, dict) or set(value) != {"tenant_id", "owner_id"}:
            raise CrawlOperationError("exact owner scope is required")
        return {key: _text(value[key], 256, key) for key in value}

    @staticmethod
    def _consent(value):
        fields = {"consent_id", "capture_acknowledged", "source_rights_acknowledged", "expires_at"}
        if (
            not isinstance(value, dict)
            or set(value) != fields
            or value.get("capture_acknowledged") is not True
            or value.get("source_rights_acknowledged") is not True
        ):
            raise CrawlOperationError("explicit capture and source-rights acknowledgement required")
        return {
            "consent_id": _text(value["consent_id"], 256, "consent id"),
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": _number(value["expires_at"], 0, 1e12, "consent expiry"),
        }

    def _configure(self, fetcher):
        self.request = CrawlRequest.from_dict(self._state["binding"]["request"])
        self.policy = CrawlPolicy(
            allowed_hosts=frozenset(self.request.allowed_hosts),
            max_depth=self.request.max_depth,
            max_response_bytes=self.request.max_response_bytes,
            min_host_delay_seconds=self.request.min_host_delay_seconds,
        )
        self.fetcher = fetcher or SafeHttpFetcher(
            timeout_seconds=10, allowed_hosts=frozenset(self.request.allowed_hosts)
        )

    @classmethod
    def from_snapshot(cls, snapshot, *, fetcher=None):
        if not isinstance(snapshot, dict) or len(_json(snapshot)) > MAX_SNAPSHOT_BYTES:
            raise CrawlOperationError("invalid or oversized crawl snapshot")
        state = copy.deepcopy(snapshot)
        supplied = state.pop("snapshot_digest", None)
        if set(state) != {
            "schema_version",
            "binding",
            "run_id",
            "state",
            "sequence",
            "usage",
            "frontier",
            "seen",
            "host_ready",
            "robots",
            "sources",
            "events",
            "stop_reason",
            "pending_dispatch",
        }:
            raise CrawlOperationError("crawl snapshot fields mismatch")
        if supplied != _digest(state) or state.get("schema_version") != SCHEMA:
            raise CrawlOperationError("crawl snapshot integrity mismatch")
        binding = state.get("binding", {})
        if set(binding) != {"request", "request_digest", "code_digest", "scope", "consent"}:
            raise CrawlOperationError("crawl binding fields mismatch")
        request = CrawlRequest.from_dict(binding["request"])
        cls._scope(binding["scope"])
        cls._consent(binding["consent"])
        if (
            binding["request_digest"] != _digest(request.as_dict())
            or binding["code_digest"] != implementation_digest()
            or state.get("run_id") != _digest(binding)
        ):
            raise CrawlOperationError("crawl request, runtime or scope binding changed")
        if state.get("state") not in _STATES:
            raise CrawlOperationError("unknown crawl state")
        _integer(state.get("sequence"), 0, 10000, "sequence")
        usage = state.get("usage", {})
        if set(usage) != {"requests", "bytes", "reserved_bytes", "documents", "failures"}:
            raise CrawlOperationError("usage fields mismatch")
        for key, maximum in (
            ("requests", request.max_requests),
            ("bytes", request.max_total_bytes),
            ("reserved_bytes", request.max_total_bytes),
            ("documents", request.max_documents),
            ("failures", request.max_requests),
        ):
            _integer(usage[key], 0, maximum, key)
        if (
            usage["bytes"] + usage["reserved_bytes"] > request.max_total_bytes
            or usage["failures"] > usage["requests"]
        ):
            raise CrawlOperationError("cumulative usage exceeds admission")
        if (
            not isinstance(state.get("frontier"), list)
            or len(state["frontier"]) > MAX_FRONTIER
            or not isinstance(state.get("seen"), list)
            or len(state["seen"]) > 1024
        ):
            raise CrawlOperationError("crawl frontier bound exceeded")
        run = cls()
        run._state = state
        run._configure(fetcher)
        seen = set()
        for item in state["frontier"]:
            if not isinstance(item, dict) or set(item) != {
                "url",
                "original_url",
                "depth",
                "parent_url",
                "attempts",
                "ready_at",
                "redirects",
            }:
                raise CrawlOperationError("invalid frontier item")
            for key in ("url", "original_url"):
                run._admit(item[key])
            if item["url"] in seen:
                raise CrawlOperationError("duplicate frontier URL")
            seen.add(item["url"])
            if item["parent_url"] is not None:
                run._admit(item["parent_url"])
            _integer(item["depth"], 0, request.max_depth, "depth")
            _integer(item["attempts"], 0, 3, "retry attempts")
            _number(item["ready_at"], 0, 1e12, "ready time")
            if not isinstance(item["redirects"], list) or len(item["redirects"]) > 5:
                raise CrawlOperationError("redirect chain bound exceeded")
            for url in item["redirects"]:
                run._admit(url)
        pending = state.get("pending_dispatch")
        if pending is not None:
            if not isinstance(pending, dict) or set(pending) != {
                "url",
                "item_url",
                "original_url",
                "limit",
                "sequence",
                "started_at",
            }:
                raise CrawlOperationError("invalid pending dispatch")
            for key in ("url", "item_url", "original_url"):
                run._admit(pending[key])
            _integer(pending["limit"], 1, request.max_response_bytes, "reserved byte cap")
            _integer(pending["sequence"], 1, state["sequence"], "dispatch sequence")
            _number(pending["started_at"], 0, 1e12, "dispatch timestamp")
            if (
                pending["limit"] > usage["reserved_bytes"]
                or usage["requests"] < 1
                or not any(
                    row["url"] == pending["item_url"] and row["original_url"] == pending["original_url"]
                    for row in state["frontier"]
                )
            ):
                raise CrawlOperationError("pending dispatch is not bound to reserved work")
        if len(set(state["seen"])) != len(state["seen"]):
            raise CrawlOperationError("duplicate visited URL")
        for url in state["seen"]:
            run._admit(url)
        if not isinstance(state.get("host_ready"), dict) or set(state["host_ready"]) - set(
            request.allowed_hosts
        ):
            raise CrawlOperationError("invalid host scheduling state")
        for value in state["host_ready"].values():
            _number(value, 0, 1e12, "host readiness")
        if not isinstance(state.get("robots"), dict) or len(state["robots"]) > 32:
            raise CrawlOperationError("invalid robots state")
        for origin, row in state["robots"].items():
            run._admit(origin + "/robots.txt")
            if not isinstance(row, dict) or set(row) != {
                "text",
                "fetched_at",
                "status",
                "raw_body_hash",
                "pending_url",
                "redirects",
            }:
                raise CrawlOperationError("invalid robots receipt")
            if row["text"] is not None:
                _text(row["text"], 65536, "robots text", empty=True)
            _number(row["fetched_at"], 0, 1e12, "robots timestamp")
            _integer(row["status"], 0, 599, "robots status")
            run._admit(row["pending_url"])
            if not isinstance(row["redirects"], list) or len(row["redirects"]) > 5:
                raise CrawlOperationError("robots redirect bound exceeded")
            for url in row["redirects"]:
                run._admit(url)
        sources = state.get("sources")
        if not isinstance(sources, dict) or len(sources) != usage["documents"]:
            raise CrawlOperationError("source counter mismatch")
        for source_id, source in sources.items():
            if (
                not isinstance(source, dict)
                or source.get("source_id") != source_id
                or source_id
                != _digest({"url": source.get("canonical_url"), "content_hash": source.get("content_hash")})
            ):
                raise CrawlOperationError("source identity mismatch")
            run._admit(source["canonical_url"])
            run._admit(source["fetched_url"])
            text = _text(source.get("text"), MAX_TEXT_BYTES, "preserved source text")
            if (
                source.get("preserved_text_hash") != hashlib.sha256(text.encode()).hexdigest()
                or source.get("review_state") != "unreviewed"
                or source.get("provenance", {}).get("binding_digest") != _digest(binding)
            ):
                raise CrawlOperationError("source evidence integrity mismatch")
            for key in ("content_hash", "raw_body_hash"):
                if not isinstance(source.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", source[key]):
                    raise CrawlOperationError("invalid source digest")
            if type(source.get("text_truncated")) is not bool or (
                not source["text_truncated"] and source["content_hash"] != source["preserved_text_hash"]
            ):
                raise CrawlOperationError("source preservation mismatch")
            _text(source.get("title"), 4000, "source title", empty=True)
            _number(source.get("fetched_at"), 0, 1e12, "source timestamp")
            provenance = source["provenance"]
            if (
                source.get("content_type") not in run.policy.allowed_content_types
                or provenance.get("schema") != "skeleton.ai.crawl.provenance.v1"
                or type(provenance.get("status")) is not int
                or not 200 <= provenance["status"] < 300
            ):
                raise CrawlOperationError("invalid source acquisition receipt")
            for key in ("canonical_url", "fetched_url", "content_hash", "fetched_at", "raw_body_hash"):
                if provenance.get(key) != source[key]:
                    raise CrawlOperationError("source acquisition identity mismatch")
            if (
                provenance.get("consent_id") != binding["consent"]["consent_id"]
                or provenance.get("training_permission") is not False
                or provenance.get("raw_bytes_retained") is not False
                or provenance.get("source_status") != "unreviewed_external_capture"
            ):
                raise CrawlOperationError("source authority escalation denied")
            fragment = CrawlDocument(
                source["canonical_url"],
                source["fetched_url"],
                source["title"],
                text,
                source["content_type"],
                source["content_hash"],
                source["fetched_at"],
                _source_score(source["canonical_url"], text, provenance["status"]),
                provenance,
                (),
            )
            if _digest(source.get("observation")) != _digest(
                asdict(EvidenceObservation.from_document(fragment, request.query))
            ):
                raise CrawlOperationError("source observation mismatch")
        events = state.get("events")
        if not isinstance(events, list) or len(events) > 64:
            raise CrawlOperationError("event history bound exceeded")
        last = 0
        for event in events:
            raw = dict(event)
            supplied = raw.pop("event_digest", None)
            if (
                supplied != _digest(raw)
                or type(raw.get("sequence")) is not int
                or not last < raw["sequence"] <= state["sequence"]
            ):
                raise CrawlOperationError("event integrity mismatch")
            last = raw["sequence"]
        return run

    def _admit(self, url):
        normalized = _url(url)
        if normalized != url or not self.policy.admits(normalized):
            raise CrawlOperationError("URL is outside admitted source scope")
        return normalized

    def _enqueue(self, url, *, depth, parent_url):
        try:
            url = self._admit(canonicalize_url(url, base=parent_url))
        except (ValueError, UnicodeError):
            return False
        state = self._state
        if (
            depth > self.request.max_depth
            or len(state["frontier"]) >= MAX_FRONTIER
            or url in state["seen"]
            or any(row["url"] == url for row in state["frontier"])
        ):
            return False
        if sum(len(_json(row)) for row in state["frontier"]) + 3 * len(url.encode()) + 512 > 262144:
            return False
        state["frontier"].append(
            {
                "url": url,
                "original_url": url,
                "depth": depth,
                "parent_url": parent_url,
                "attempts": 0,
                "ready_at": 0,
                "redirects": [],
            }
        )
        return True

    def snapshot(self):
        value = copy.deepcopy(self._state)
        value["snapshot_digest"] = _digest(value)
        if len(_json(value)) > MAX_SNAPSHOT_BYTES:
            raise CrawlOperationError("crawl snapshot exceeds storage bound")
        return value

    def status(self):
        state = self._state
        now = time.time()
        ready = [
            max(row["ready_at"], state["host_ready"].get(urlsplit(row["url"]).hostname, 0))
            for row in state["frontier"]
        ]
        return {
            "run_id": state["run_id"],
            "state": state["state"],
            "sequence": state["sequence"],
            "request_digest": state["binding"]["request_digest"],
            "code_digest": state["binding"]["code_digest"],
            "usage": dict(state["usage"]),
            "frontier_count": len(state["frontier"]),
            "next_ready_at": min(ready) if ready else None,
            "source_count": len(state["sources"]),
            "stop_reason": state["stop_reason"],
            "consent_expires_at": state["binding"]["consent"]["expires_at"],
            "consent_current": now < state["binding"]["consent"]["expires_at"],
            "queue": [
                {
                    "url": row["url"],
                    "depth": row["depth"],
                    "attempts": row["attempts"],
                    "ready_at": row["ready_at"],
                }
                for row in state["frontier"][:32]
            ],
            "snapshot_digest": self.snapshot()["snapshot_digest"],
        }

    def sources(self):
        return [copy.deepcopy(row) for row in self._state["sources"].values()]

    def source_read(self, source_id):
        row = self._state["sources"].get(source_id)
        if row is None:
            raise CrawlOperationError("captured source not found")
        return copy.deepcopy(row)

    def search(self, query, *, limit=8):
        """Return real captured passages as untrusted, attributable evidence."""
        _text(query, 1024, "search query")
        if len(query) > 512:
            raise CrawlOperationError("search query exceeds lexical ranker bound")
        _integer(limit, 1, 8, "search limit")
        hits = []
        for source in self._state["sources"].values():
            for passage in rank_query_passages(source["text"], query, limit=limit):
                span = passage.span
                hits.append(
                    {
                        "source_id": source["source_id"],
                        "canonical_url": source["canonical_url"],
                        "title": source["title"],
                        "content_hash": source["content_hash"],
                        "preserved_text_hash": source["preserved_text_hash"],
                        "passage_hash": hashlib.sha256(span.text.encode()).hexdigest(),
                        "start": span.start,
                        "end": span.end,
                        "text": span.text,
                        "lexical_score": passage.weighted_score,
                        "review_state": "unreviewed",
                        "authority": "external_evidence_only",
                        "instruction_risks": [
                            asdict(signal) for signal in scan_untrusted_instructions(span.text, limit=16)
                        ],
                    }
                )
        hits.sort(key=lambda row: (-row["lexical_score"], row["source_id"], row["start"]))
        result = {
            "schema_version": "skeleton.ai.dragon.crawl_evidence.v1",
            "run_id": self._state["run_id"],
            "query": query,
            "hits": hits[:limit],
            "verified_knowledge": False,
            "training_permission": False,
        }
        result["evidence_digest"] = _digest(result)
        return result

    def _event(self, kind, *, now, url=None, source_id=None, reason=None):
        self._state["sequence"] += 1
        event = {
            "sequence": self._state["sequence"],
            "kind": kind,
            "at": now,
            "url": url,
            "source_id": source_id,
            "reason": reason,
            "usage": dict(self._state["usage"]),
        }
        event["event_digest"] = _digest(event)
        self._state["events"] = (self._state["events"] + [event])[-64:]
        return event

    def _control(self, action, now=None):
        at = time.time() if now is None else _number(now, 0, 1e12, "time")
        state = self._state["state"]
        target = {"pause": "paused", "resume": "ready", "cancel": "cancelled"}[action]
        if state == target:
            return self.status()
        if state in _TERMINAL or (action == "resume" and state not in {"paused", "failed"}):
            raise CrawlOperationError("invalid crawl control transition")
        if action == "resume" and at >= self._state["binding"]["consent"]["expires_at"]:
            raise CrawlOperationError("capture consent expired")
        self._state["state"] = target
        self._state["stop_reason"] = "operator_" + action if action != "resume" else None
        self._event(action, now=at)
        return self.status()

    def pause(self, *, now=None):
        return self._control("pause", now)

    def resume(self, *, now=None):
        return self._control("resume", now)

    def cancel(self, *, now=None):
        return self._control("cancel", now)

    def _authority(self, authorize, cancelled):
        if cancelled and cancelled():
            raise CrawlOperationError("crawl slice cancelled")
        if time.time() >= self._state["binding"]["consent"]["expires_at"]:
            raise CrawlOperationError("capture consent expired")
        if implementation_digest() != self._state["binding"]["code_digest"]:
            raise CrawlOperationError("crawler implementation changed during capture")
        if authorize:
            authorize()

    def _robots_cache(self, origin):
        row = self._state["robots"].get(origin)
        if row is None or row["text"] is None:
            return None
        cache = RobotsCache(self.policy.user_agent)
        cache.install(origin, row["text"], fetched_at=row["fetched_at"])
        return cache

    def _finish_item(self, item):
        self._state["frontier"].remove(item)
        for url in (item["original_url"], item["url"]):
            if url not in self._state["seen"]:
                self._state["seen"].append(url)

    def _retry(self, item, now, *, retry_after=None):
        if item["attempts"] >= 3:
            self._finish_item(item)
            return False
        item["attempts"] += 1
        delay = min(300, max(1, retry_after if retry_after is not None else 2 ** item["attempts"]))
        item["ready_at"] = now + delay
        return True

    def _persist(self, event):
        try:
            self._authority(self._authorize, self._cancelled)
            snapshot = self.snapshot()
            if self._on_checkpoint:
                self._on_checkpoint(snapshot, copy.deepcopy(event))
        except Exception as exc:
            raise _CheckpointInterrupted("crawl authority or checkpoint rejected") from exc
        self._rollback_state = copy.deepcopy(self._state)

    def _fetch(self, url, *, limit, item):
        self._admit(url)
        self._state["usage"]["requests"] += 1
        self._state["usage"]["reserved_bytes"] += limit
        started = time.time()
        self._state["pending_dispatch"] = {
            "url": url,
            "item_url": item["url"],
            "original_url": item["original_url"],
            "limit": limit,
            "sequence": self._state["sequence"] + 1,
            "started_at": started,
        }
        self._persist(
            self._event(
                "dispatch_reserved",
                now=started,
                url=url,
                reason="request_and_byte_cap_reserved_before_network",
            )
        )
        try:
            self._authority(self._authorize, self._cancelled)
        except Exception as exc:
            raise _CheckpointInterrupted("crawl dispatch authority rejected") from exc
        timeout = getattr(self.fetcher, "timeout_seconds", None)
        if timeout is not None:
            self.fetcher.timeout_seconds = min(timeout, max(0.01, self._slice_deadline - time.monotonic()))
        try:
            response = self.fetcher.fetch_once(url, user_agent=self.policy.user_agent, max_bytes=limit)
        finally:
            if timeout is not None:
                self.fetcher.timeout_seconds = timeout
        if (
            not isinstance(response, FetchResponse)
            or canonicalize_url(response.url) != url
            or type(response.status) is not int
            or not 100 <= response.status <= 599
            or not isinstance(response.body, bytes)
            or len(response.body) > limit
        ):
            raise CrawlOperationError("transport response violates admitted request")
        _number(response.fetched_at, started - 300, time.time() + 300, "response timestamp")
        self._state["usage"]["bytes"] += len(response.body)
        self._state["usage"]["reserved_bytes"] -= limit
        self._state["pending_dispatch"] = None
        return response

    def _step(self, now):
        state = self._state
        item = next(
            (
                row
                for row in state["frontier"]
                if max(row["ready_at"], state["host_ready"].get(urlsplit(row["url"]).hostname, 0)) <= now
            ),
            None,
        )
        if item is None:
            return None
        url = item["url"]
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        robots = state["robots"].get(origin)
        needs_robots = robots is None or robots["text"] is None or now - robots["fetched_at"] >= 86400
        if needs_robots:
            if robots is None:
                robots = {
                    "text": None,
                    "fetched_at": 0,
                    "status": 0,
                    "raw_body_hash": None,
                    "pending_url": origin + "/robots.txt",
                    "redirects": [],
                }
                state["robots"][origin] = robots
            fetch_url = robots["pending_url"]
        else:
            cache = self._robots_cache(origin)
            if not cache.allowed(url):
                self._finish_item(item)
                return self._event("rejected", now=now, url=url, reason="robots_denied")
            fetch_url = url
        host = urlsplit(fetch_url).hostname
        if state["host_ready"].get(host, 0) > now:
            item["ready_at"] = state["host_ready"][host]
            return None
        delay = self.request.min_host_delay_seconds
        cache = self._robots_cache(origin)
        if cache is not None:
            delay = max(delay, cache.crawl_delay(url) or 0)
        state["host_ready"][host] = now + delay
        remaining = self.request.max_total_bytes - state["usage"]["bytes"] - state["usage"]["reserved_bytes"]
        limit = min(
            self.request.max_response_bytes,
            remaining,
            65536 if needs_robots else self.request.max_response_bytes,
        )
        try:
            response = self._fetch(fetch_url, limit=limit, item=item)
        except _CheckpointInterrupted:
            raise
        except Exception as exc:  # noqa: BLE001 -- failed transport attempts retain budget
            state["usage"]["failures"] += 1
            # The attempt consumed a dispatch slot; remote bytes discarded by a
            # failed transport are unknown, so reserve its entire admitted cap.
            state["pending_dispatch"] = None
            retained = self._retry(item, now)
            return self._event(
                "error",
                now=time.time(),
                url=fetch_url,
                reason=f"{type(exc).__name__}:{'retry_scheduled' if retained else 'retry_exhausted'}",
            )
        now = time.time()
        state["host_ready"][host] = max(state["host_ready"][host], now + delay)
        if response.status in _REDIRECTS:
            chain = robots["redirects"] if needs_robots else item["redirects"]
            try:
                destination = self._admit(
                    canonicalize_url(response.headers.get("location", ""), base=fetch_url)
                )
                if len(chain) >= 5 or destination == fetch_url or destination in chain:
                    raise CrawlOperationError("redirect chain rejected")
            except (ValueError, UnicodeError):
                self._finish_item(item)
                return self._event(
                    "rejected", now=now, url=fetch_url, reason="redirect_outside_scope_or_loop"
                )
            chain.append(fetch_url)
            if needs_robots:
                robots["pending_url"] = destination
            else:
                item["url"] = destination
            return self._event("redirect", now=now, url=fetch_url, reason=destination)
        if response.status in _RETRY:
            retry_after = CrawlEngine._retry_after(response.headers, now=now)
            if retry_after is not None and not math.isfinite(retry_after):
                retry_after = None
            retained = self._retry(item, now, retry_after=retry_after)
            return self._event(
                "retry",
                now=now,
                url=fetch_url,
                reason=f"http_{response.status}:{'scheduled' if retained else 'exhausted'}",
            )
        if needs_robots:
            robots["status"] = response.status
            robots["fetched_at"] = now
            robots["raw_body_hash"] = hashlib.sha256(response.body).hexdigest()
            ctype = response.headers.get("content-type", "text/plain").split(";", 1)[0].strip().lower()
            if response.status in {404, 410}:
                robots["text"] = ""
            elif response.status == 200 and ctype in {"text/plain", "text/html"}:
                text = response.body.decode("utf-8", errors="replace")
                retained = sum(
                    len(row["text"].encode()) for row in state["robots"].values() if row["text"] is not None
                )
                # Never truncate robots rules: a dropped Disallow could grant
                # access. Refuse this origin if the bounded cache cannot fit.
                robots["text"] = (
                    text
                    if len(text.encode()) <= 65536 and retained + len(text.encode()) <= 262144
                    else "User-agent: *\nDisallow: /"
                )
            else:
                robots["text"] = "User-agent: *\nDisallow: /"
            return self._event("robots", now=now, url=fetch_url, reason=f"http_{response.status}")
        ctype = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        self._finish_item(item)
        if not 200 <= response.status < 300 or ctype not in self.policy.allowed_content_types:
            return self._event(
                "rejected", now=now, url=url, reason=f"http_{response.status}_or_unsupported_type"
            )
        doc = extract_document(
            response, item["original_url"], max_links=128, max_text_chars=self.request.max_response_bytes
        )
        if doc is None:
            return self._event("rejected", now=now, url=url, reason="empty_document")
        if any(source["content_hash"] == doc.content_hash for source in state["sources"].values()):
            for link in doc.links:
                self._enqueue(link, depth=item["depth"] + 1, parent_url=url)
            return self._event("duplicate", now=now, url=url, reason=doc.content_hash)
        text_bytes = doc.text.encode("utf-8")
        text = text_bytes[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
        source_id = _digest({"url": doc.canonical_url, "content_hash": doc.content_hash})
        observed_doc = type(doc)(**{**doc.__dict__, "text": text})
        observation = asdict(EvidenceObservation.from_document(observed_doc, self.request.query))
        provenance = {
            **doc.provenance,
            "binding_digest": _digest(state["binding"]),
            "consent_id": state["binding"]["consent"]["consent_id"],
            "transport_mode": getattr(self.fetcher, "transport_mode", "caller_supplied_transport"),
            "source_status": "unreviewed_external_capture",
            "training_permission": False,
            "raw_bytes_retained": False,
            "requested_url": item["original_url"],
            "redirect_chain": list(item["redirects"]),
            "parent_url": item["parent_url"],
        }
        state["sources"][source_id] = {
            "source_id": source_id,
            "canonical_url": doc.canonical_url,
            "fetched_url": doc.fetched_url,
            "title": doc.title,
            "text": text,
            "content_hash": doc.content_hash,
            "raw_body_hash": doc.provenance["raw_body_hash"],
            "preserved_text_hash": hashlib.sha256(text.encode()).hexdigest(),
            "text_truncated": len(text.encode()) < len(text_bytes),
            "content_type": doc.content_type,
            "fetched_at": doc.fetched_at,
            "review_state": "unreviewed",
            "provenance": provenance,
            "observation": observation,
        }
        state["usage"]["documents"] += 1
        for link in doc.links:
            self._enqueue(link, depth=item["depth"] + 1, parent_url=url)
        return self._event("captured", now=now, url=url, source_id=source_id)

    def run_slice(self, *, max_steps=4, max_seconds=40, authorize=None, cancelled=None, on_checkpoint=None):
        _integer(max_steps, 1, 4, "slice steps")
        _number(max_seconds, 0.1, 45, "slice seconds")
        if self._state["state"] not in {"ready", "running"}:
            return {**self.status(), "slice_events": [], "slice_steps": 0}
        start = time.monotonic()
        self._slice_deadline = start + max_seconds
        self._authorize, self._cancelled, self._on_checkpoint = authorize, cancelled, on_checkpoint
        events = []
        for _ in range(max_steps):
            if time.monotonic() - start >= max_seconds:
                break
            self._authority(authorize, cancelled)
            before = copy.deepcopy(self._state)
            self._rollback_state = before
            try:
                self._state["state"] = "running"
                usage = self._state["usage"]
                pending = self._state["pending_dispatch"]
                if pending is not None:
                    item = next(
                        row
                        for row in self._state["frontier"]
                        if row["url"] == pending["item_url"]
                        and row["original_url"] == pending["original_url"]
                    )
                    self._state["pending_dispatch"] = None
                    usage["failures"] += 1
                    self._retry(item, time.time())
                    event = self._event(
                        "interrupted_dispatch",
                        now=time.time(),
                        url=pending["url"],
                        reason="unknown_outcome_reserved_cap_retained",
                    )
                elif (
                    usage["requests"] >= self.request.max_requests
                    or usage["bytes"] + usage["reserved_bytes"] >= self.request.max_total_bytes
                    or usage["documents"] >= self.request.max_documents
                    or len(_json(self._state)) >= 3 * 1024 * 1024
                ):
                    self._state["state"] = "budget_exhausted"
                    self._state["stop_reason"] = (
                        "snapshot_storage_budget"
                        if len(_json(self._state)) >= 3 * 1024 * 1024
                        else "cumulative_budget"
                    )
                    event = self._event("stopped", now=time.time(), reason=self._state["stop_reason"])
                elif not self._state["frontier"]:
                    self._state["state"] = "completed"
                    self._state["stop_reason"] = "frontier_drained"
                    event = self._event("completed", now=time.time(), reason="frontier_drained")
                else:
                    event = self._step(time.time())
                    if event is None:
                        self._state = before
                        break
                    if not self._state["frontier"]:
                        self._state["state"] = "completed"
                        self._state["stop_reason"] = "frontier_drained"
                self._persist(event)
                events.append(event)
            except BaseException:
                self._state = self._rollback_state
                raise
            if self._state["state"] in _TERMINAL:
                break
        return {**self.status(), "slice_events": copy.deepcopy(events), "slice_steps": len(events)}
