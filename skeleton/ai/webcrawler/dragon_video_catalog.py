"""Provider-neutral, bounded discovery catalog ingestion.

A trusted caller supplies already retrieved metadata. This module does not fetch
URLs, scrape providers, download media, or authorize ingestion.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable, Mapping
from .dragon_video_discovery import VideoCandidate
from .dragon_video_history import canonical_video_url


@dataclass(frozen=True)
class CatalogPolicy:
    max_candidates: int = 1000
    max_tags_per_candidate: int = 24
    max_title_chars: int = 240
    allow_providers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogReceipt:
    candidates: tuple[VideoCandidate, ...]
    accepted: int
    rejected: int
    fingerprint: str


def ingest_video_catalog(
    rows: Iterable[Mapping[str, object]],
    *,
    policy: CatalogPolicy = CatalogPolicy(),
    authorized: bool = False,
) -> CatalogReceipt:
    if not authorized:
        raise PermissionError("video discovery catalog ingestion requires authorization")
    if not (1 <= policy.max_candidates <= 10000 and
            1 <= policy.max_tags_per_candidate <= 100 and
            1 <= policy.max_title_chars <= 1000):
        raise ValueError("invalid catalog policy")
    accepted: dict[str, VideoCandidate] = {}
    rejected = 0
    for index, row in enumerate(rows):
        if index >= policy.max_candidates:
            raise ValueError("catalog processing budget exceeded")
        try:
            if not isinstance(row, Mapping):
                raise ValueError("invalid catalog entry")
            url, title, provider = row["url"], row["title"], row["provider"]
            tags = row["tags"]
            if not isinstance(url, str) or not isinstance(title, str) or not isinstance(provider, str):
                raise ValueError("invalid catalog metadata")
            if not isinstance(tags, (tuple, list)) or len(tags) > policy.max_tags_per_candidate:
                raise ValueError("invalid catalog tags")
            if not title.strip() or len(title) > policy.max_title_chars:
                raise ValueError("invalid title")
            if not provider.strip() or len(provider) > 100:
                raise ValueError("invalid provider")
            if policy.allow_providers and provider not in policy.allow_providers:
                raise ValueError("provider not allowed")
            if any(not isinstance(t, str) or not t.strip() or len(t) > 64 for t in tags):
                raise ValueError("invalid tag")
            published = row.get("published_at")
            if published is not None and (not isinstance(published, (int, float)) or not isfinite(published)):
                raise ValueError("invalid publication time")
            canonical = canonical_video_url(url)
            normalized_tags = tuple(sorted(set(" ".join(t.casefold().split()) for t in tags)))
            candidate = VideoCandidate(canonical, title.strip(), normalized_tags, provider,
                                       float(published) if published is not None else None)
            existing = accepted.get(canonical)
            if existing is None or (candidate.provider, candidate.title) < (existing.provider, existing.title):
                accepted[canonical] = candidate
        except (KeyError, ValueError, TypeError):
            rejected += 1
    candidates = tuple(sorted(accepted.values(), key=lambda item: item.url))
    digest = sha256()
    for candidate in candidates:
        digest.update(repr(candidate).encode("utf-8"))
        digest.update(b"\n")
    return CatalogReceipt(candidates, len(candidates), rejected, digest.hexdigest())
