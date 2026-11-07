"""Ephemeral, Unicode-span-preserving lexical index over current crawl snapshots.

This is a rebuildable, nonpersistent projection, not a second knowledge
database. Every query revalidates its snapshot, current grant and caller-
supplied authoritative source withdrawals before returning page text.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import log
from typing import Iterable
import re

from ..dragon_mission_quality import segment_passages
from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope
from .evidence import inspect_campaign_evidence
from .query_lattice import passage_matches_operator_terms


_WORDS = re.compile(r"[^\W_]{2,}", re.UNICODE)
_STOP = frozenset(("the", "and", "for", "from", "with", "that", "this", "into", "are", "was", "their"))


@dataclass(frozen=True)
class IndexedPassage:
    source_id: str
    canonical_url: str
    full_content_hash: str
    preserved_text_hash: str
    start: int
    end: int
    text: str
    passage_hash: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class EphemeralIndex:
    mandate_digest: str
    source_snapshot_digest: str
    created_at: float
    admitted_source_ids: tuple[str, ...]
    passages: tuple[IndexedPassage, ...]
    rejected_source_ids: tuple[str, ...]
    index_digest: str
    persistent_storage: bool = False
    factual_verification: bool = False


@dataclass(frozen=True)
class IndexedHit:
    source_id: str
    canonical_url: str
    source_hash: str
    passage_hash: str
    start: int
    end: int
    matched_terms: tuple[str, ...]
    score: float
    text: str
    trust: str = "unreviewed_external_content"


@dataclass(frozen=True)
class IndexedSearch:
    query: str
    mode: str
    hits: tuple[IndexedHit, ...]
    examined_passages: int
    source_snapshot_digest: str
    result_digest: str
    publication_authorized: bool = False


def _terms(text: str) -> tuple[str, ...]:
    return tuple(word.casefold() for word in _WORDS.findall(text)
                 if word.casefold() not in _STOP)


def build_ephemeral_index(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    *, now: float,
    authorized: bool,
    revoked_source_ids: Iterable[str] = (),
    max_passages: int = 2048,
) -> EphemeralIndex:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if type(max_passages) is not int or not 1 <= max_passages <= 4096:
        raise ValueError("invalid ephemeral index capacity")
    run = CrawlRun.from_snapshot(snapshot)
    canonical = run.snapshot()
    revoked = tuple(revoked_source_ids)
    if len(revoked) != len(set(revoked)) or any(
        ident not in canonical["sources"] for ident in revoked
    ):
        raise PermissionError("withdrawal identity outside current snapshot")
    observed = inspect_campaign_evidence(
        mandate, run.sources(), now=now, authorized=authorized,
        revoked_source_ids=revoked,
    )
    admitted = {x.source_id: x for x in observed.sources if x.inspectable}
    rows = []
    rejected = {source_id for source_id, _ in observed.rejected_sources}
    rejected.update(
        x.source_id for x in observed.sources if not x.inspectable
    )
    for record in run.sources():
        source_id = record["source_id"]
        if source_id not in admitted:
            continue
        text = record["text"]
        for span in segment_passages(
            text, max_chars=600, overlap=30,
            max_segments=128,
        ):
            terms = tuple(sorted(set(_terms(span.text))))
            if not terms:
                continue
            if len(rows) >= max_passages:
                raise ValueError("ephemeral passage index capacity exceeded")
            rows.append(IndexedPassage(
                source_id=source_id,
                canonical_url=record["canonical_url"],
                full_content_hash=record["content_hash"],
                preserved_text_hash=record["preserved_text_hash"],
                start=span.start,
                end=span.end,
                text=span.text,
                passage_hash=sha256(span.text.encode("utf-8")).hexdigest(),
                terms=terms,
            ))
    rows.sort(key=lambda x: (x.source_id, x.start, x.end))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "at": now,
        "passages": [
            (x.source_id, x.start, x.end, x.passage_hash)
            for x in rows
        ],
        "rejected": sorted(rejected),
    }
    return EphemeralIndex(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        created_at=now,
        admitted_source_ids=tuple(sorted(admitted)),
        passages=tuple(rows),
        rejected_source_ids=tuple(sorted(rejected)),
        index_digest=digest(payload),
    )


def search_ephemeral_index(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    index: EphemeralIndex,
    query: str,
    *,
    now: float,
    authorized: bool,
    revoked_source_ids: Iterable[str] = (),
    mode: str = "all",
    limit: int = 8,
    max_per_source: int = 3,
    required_terms: tuple[str, ...] = (),
    blocked_terms: tuple[str, ...] = (),
) -> IndexedSearch:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(index, EphemeralIndex):
        raise TypeError("ephemeral index required")
    if index.mandate_digest != mandate.fingerprint:
        raise PermissionError("cross-mandate index use denied")
    run = CrawlRun.from_snapshot(snapshot)
    current = run.snapshot()
    if index.source_snapshot_digest != current["snapshot_digest"]:
        raise PermissionError("index source snapshot has changed")
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError("invalid index result limit")
    if type(max_per_source) is not int or not 1 <= max_per_source <= 8:
        raise ValueError("invalid source diversity cap")
    if mode not in ("all", "any"):
        raise ValueError("invalid lexical query mode")
    if not isinstance(query, str) or not query.strip() or len(query.encode("utf-8")) > 512:
        raise ValueError("invalid query")
    tokens = tuple(sorted(set(_terms(query))))
    if not 1 <= len(tokens) <= 16:
        raise ValueError("query token capacity exceeded")
    # Prove the exact literal filter contract before scanning any indexed
    # source. Constraints must not be applied only after the top-k window:
    # otherwise a broad query could fill the candidate limit with blocked
    # passages and bury genuinely eligible passages.
    passage_matches_operator_terms("", required_terms, blocked_terms)
    if set(required_terms) & set(blocked_terms):
        raise ValueError("contradictory per-passage filter")
    revoked = set(revoked_source_ids)
    if any(x not in current["sources"] for x in revoked):
        raise PermissionError("unknown revoked source")
    # Re-check current text integrity for all retained source identities;
    # caller must derive current withdrawals from canonical source-use policy.
    accepted = []
    for passage in index.passages:
        if passage.source_id in revoked:
            continue
        source = current["sources"].get(passage.source_id)
        if source is None:
            raise PermissionError("missing indexed source")
        # Reject caller-constructed index tuples with negative/Boolean spans,
        # swapped source URLs, an invented passage digest or altered term
        # vectors. Downstream citations cannot trust ambiguous offsets just
        # because Python's negative indexing happens to return some text.
        if (
            type(passage.start) is not int or type(passage.end) is not int
            or passage.start < 0 or passage.end <= passage.start
            or passage.end > len(source["text"])
            or passage.end - passage.start > 600
            or source["content_hash"] != passage.full_content_hash
            or source["preserved_text_hash"] != passage.preserved_text_hash
            or source["canonical_url"] != passage.canonical_url
            or source["text"][passage.start:passage.end] != passage.text
            or sha256(passage.text.encode("utf-8")).hexdigest() != passage.passage_hash
            or tuple(sorted(set(_terms(passage.text)))) != passage.terms
        ):
            raise PermissionError("indexed passage span/hash/terms no longer match source")
        if (required_terms or blocked_terms) and not passage_matches_operator_terms(
            passage.text, required_terms, blocked_terms,
        ):
            continue
        seen = frozenset(passage.terms) & set(tokens)
        if not seen or (mode == "all" and len(seen) != len(tokens)):
            continue
        coverage = len(seen) / len(tokens)
        density = len(seen) / max(1, len(passage.terms))
        score = round(0.85 * coverage + 0.15 * density, 8)
        accepted.append(IndexedHit(
            source_id=passage.source_id,
            canonical_url=passage.canonical_url,
            source_hash=passage.full_content_hash,
            passage_hash=passage.passage_hash,
            start=passage.start, end=passage.end,
            matched_terms=tuple(sorted(seen)), score=score,
            text=passage.text,
        ))
    accepted.sort(key=lambda x: (-x.score, x.source_id, x.start))
    seen_sources: dict[str, int] = {}
    hits = []
    for hit in accepted:
        used = seen_sources.get(hit.source_id, 0)
        if used >= max_per_source:
            continue
        seen_sources[hit.source_id] = used + 1
        hits.append(hit)
        if len(hits) == limit:
            break
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": current["snapshot_digest"],
        "index": index.index_digest, "query": query, "mode": mode,
        "required_terms": required_terms, "blocked_terms": blocked_terms,
        "hits": [
            (hit.source_id, hit.start, hit.end, hit.passage_hash, hit.score)
            for hit in hits
        ],
    }
    return IndexedSearch(
        query=query, mode=mode, hits=tuple(hits),
        examined_passages=len(index.passages),
        source_snapshot_digest=current["snapshot_digest"],
        result_digest=digest(payload),
    )
