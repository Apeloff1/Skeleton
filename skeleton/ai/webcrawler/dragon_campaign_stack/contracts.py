"""Typed, bounded, non-authoritative Dragon research campaign contracts.

These plans are proposals for the existing CrawlRun owner; no network I/O,
authorization, Mongo commits or knowledge promotion occurs in this package.
Every input is treated as potentially attacker-controlled.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import isfinite
from typing import Any
from urllib.parse import urlsplit
import json

from ..core import CrawlPolicy, canonicalize_url
from ..operations import CrawlRequest


SCHEMA = "skeleton.ai.dragon.campaign.v1"
MAX_JSON_BYTES = 1_048_576


def digest(value: object) -> str:
    """Stable receipt identity; this is not authentication or a signature."""
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def bounded_text(value: object, label: str, maximum: int = 256) -> str:
    if (not isinstance(value, str) or not value.strip()
            or len(value.encode("utf-8")) > maximum
            or any(ord(c) < 32 for c in value)):
        raise ValueError("invalid " + label)
    return value


def finite(value: object, label: str, low: float = 0, high: float = 1e12) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or not low <= value <= high):
        raise ValueError("invalid " + label)
    return float(value)


def integer(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid " + label)
    return value


def exact_digest(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("invalid " + label)
    return value


@dataclass(frozen=True)
class CampaignScope:
    tenant_id: str
    owner_id: str
    consent_id: str
    expires_at: float
    allowed_hosts: tuple[str, ...]
    purpose: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "owner_id", "consent_id"):
            bounded_text(getattr(self, name), name)
        bounded_text(self.purpose, "campaign purpose", 1024)
        finite(self.expires_at, "consent expiry")
        if not isinstance(self.allowed_hosts, tuple) or not 1 <= len(self.allowed_hosts) <= 16:
            raise ValueError("invalid campaign hosts")
        hosts = []
        for entry in self.allowed_hosts:
            bounded_text(entry, "host", 253)
            try:
                name = entry.encode("idna").decode("ascii").lower()
            except UnicodeError as exc:
                raise ValueError("invalid campaign host") from exc
            # The canonical request owner is stricter than this preliminary check.
            if name != entry or name in hosts or "." not in name:
                raise ValueError("hosts must be unique canonical DNS names")
            hosts.append(name)
        if not isinstance(self.purpose, str):
            raise ValueError("invalid purpose")

    def require_current(self, now: float, *, authorized: bool) -> None:
        finite(now, "campaign clock")
        if not authorized:
            raise PermissionError("campaign requires fresh external authority")
        if now >= self.expires_at:
            raise PermissionError("campaign consent expired")

    def policy(self, *, max_response_bytes: int = 2_097_152) -> CrawlPolicy:
        integer(max_response_bytes, "response cap", 1024, 2_097_152)
        return CrawlPolicy(
            allowed_hosts=frozenset(self.allowed_hosts),
            max_response_bytes=max_response_bytes,
        )


@dataclass(frozen=True)
class CampaignLimits:
    max_candidates: int = 512
    max_dispatches: int = 32
    max_per_host: int = 8
    max_evidence: int = 64
    max_evidence_chars: int = 16_384
    max_dependency_edges: int = 512
    max_journal_entries: int = 512
    min_host_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        for name, low, high in (
            ("max_candidates", 1, 512),
            ("max_dispatches", 1, 128),
            ("max_per_host", 1, 32),
            ("max_evidence", 1, 128),
            ("max_evidence_chars", 128, 24_000),
            ("max_dependency_edges", 0, 1024),
            ("max_journal_entries", 1, 1024),
        ):
            integer(getattr(self, name), name, low, high)
        finite(self.min_host_delay_seconds, "host delay", 0.25, 30)


@dataclass(frozen=True)
class CampaignMandate:
    scope: CampaignScope
    request: CrawlRequest
    query: str
    created_at: float
    limits: CampaignLimits = CampaignLimits()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, CampaignScope):
            raise ValueError("invalid campaign scope")
        if not isinstance(self.request, CrawlRequest):
            raise ValueError("invalid crawl request")
        if not isinstance(self.limits, CampaignLimits):
            raise ValueError("invalid campaign limits")
        if not isinstance(self.query, str) or len(self.query.encode("utf-8")) > 512:
            raise ValueError("invalid campaign query")
        if any(ord(c) < 32 and c not in "\t\n" for c in self.query):
            raise ValueError("invalid campaign query")
        finite(self.created_at, "creation clock")
        if self.created_at >= self.scope.expires_at:
            raise ValueError("mandate created after consent expiry")
        if set(self.request.allowed_hosts) != set(self.scope.allowed_hosts):
            raise PermissionError("request host allowlist differs from mandate")
        if self.request.query != self.query:
            raise ValueError("campaign query must match canonical request")

    @property
    def fingerprint(self) -> str:
        return digest({
            "schema": SCHEMA,
            "scope": asdict(self.scope),
            "request": self.request.as_dict(),
            "query": self.query,
            "created_at": self.created_at,
            "limits": asdict(self.limits),
        })

    def admit(self, *, now: float, authorized: bool) -> None:
        self.scope.require_current(now, authorized=authorized)
        if now < self.created_at:
            raise ValueError("campaign clock moved before creation")


@dataclass(frozen=True)
class ResearchCandidate:
    url: str
    relevance: float
    information_gain: float
    quality: float
    expected_bytes: int
    reason: str = "unreviewed_discovery"
    parent_url: str | None = None
    depth: int = 0

    def __post_init__(self) -> None:
        canonical = canonicalize_url(self.url)
        if canonical != self.url:
            raise ValueError("noncanonical candidate URL")
        for name in ("relevance", "information_gain", "quality"):
            finite(getattr(self, name), name, 0, 1)
        integer(self.expected_bytes, "expected bytes", 1, 2_097_152)
        bounded_text(self.reason, "source reason", 128)
        integer(self.depth, "candidate depth", 0, 3)
        if self.parent_url is not None:
            parent = canonicalize_url(self.parent_url)
            if parent != self.parent_url:
                raise ValueError("noncanonical parent URL")


@dataclass(frozen=True)
class ResearchDispatch:
    url: str
    host: str
    ready_at: float
    rank: int
    score: float
    expected_bytes: int
    parent_url: str | None
    depth: int
    hint_only: bool = True


@dataclass(frozen=True)
class CampaignPlan:
    mandate_digest: str
    candidates_considered: int
    rejected: tuple[tuple[str, str], ...]
    dispatches: tuple[ResearchDispatch, ...]
    bytes_reserved: int
    requests_reserved: int
    plan_digest: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_snapshot_scope(snapshot: dict[str, object], mandate: CampaignMandate) -> None:
    """Compare the existing canonical CrawlRun binding, not caller-supplied hints."""
    if not isinstance(snapshot, dict):
        raise ValueError("missing canonical snapshot")
    binding = snapshot.get("binding")
    if not isinstance(binding, dict):
        raise ValueError("missing crawl binding")
    expected = {
        "tenant_id": mandate.scope.tenant_id,
        "owner_id": mandate.scope.owner_id,
    }
    if binding.get("scope") != expected:
        raise PermissionError("campaign owner mismatch")
    consent = binding.get("consent")
    if not isinstance(consent, dict) or (
        consent.get("consent_id") != mandate.scope.consent_id
        or consent.get("expires_at") != mandate.scope.expires_at
        or consent.get("capture_acknowledged") is not True
        or consent.get("source_rights_acknowledged") is not True
    ):
        raise PermissionError("campaign capture-consent mismatch")
    request = binding.get("request")
    if request != mandate.request.as_dict():
        raise PermissionError("campaign request changed")
    if binding.get("request_digest") != digest(request):
        raise ValueError("canonical request digest mismatch")


def validate_public_url(url: str, mandate: CampaignMandate) -> str:
    identity = canonicalize_url(url)
    p = urlsplit(identity)
    if identity != url or p.port is not None:
        # Canonicalize removes default port; original explicit port is still
        # forbidden by the canonical operations owner.
        if urlsplit(url).port is not None:
            raise PermissionError("explicit ports not admitted")
        raise ValueError("candidate URL identity mismatch")
    if p.hostname not in mandate.scope.allowed_hosts:
        raise PermissionError("host outside campaign scope")
    if not mandate.scope.policy(
        max_response_bytes=mandate.request.max_response_bytes
    ).admits(identity):
        raise PermissionError("destination outside canonical crawl policy")
    return identity
