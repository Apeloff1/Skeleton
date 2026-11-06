"""Multiple-query retrieval with bounded rank fusion and source diversity.

Every constituent search reopens and revalidates a canonical snapshot and the
currently authoritative withdrawal set. A fused hit is still untrusted web
content, not reviewed knowledge, a source license, or a model instruction.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import defaultdict
from hashlib import sha256
from math import isfinite
from typing import Iterable
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .query_lattice import QueryLattice, passage_matches_operator_terms
from .source_index import EphemeralIndex, search_ephemeral_index


@dataclass(frozen=True)
class FusedEvidence:
    source_id: str
    canonical_url: str
    source_hash: str
    passage_hash: str
    start: int
    end: int
    text: str
    score: float
    matched_objective_ids: tuple[str, ...]
    matched_queries: tuple[str, ...]
    query_rank_support: tuple[tuple[int, int], ...]
    host: str
    trust: str = "unreviewed_external_content"
    knowledge_verified: bool = False


@dataclass(frozen=True)
class RetrievalFusion:
    mandate_digest: str
    source_snapshot_digest: str
    index_digest: str
    lattice_digest: str
    excluded_sources: tuple[str, ...]
    results: tuple[FusedEvidence, ...]
    evaluated_queries: int
    matched_passages: int
    host_count: int
    total_context_chars: int
    fusion_digest: str
    publication_authorized: bool = False


def fuse_retrieval(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    index: EphemeralIndex,
    lattice: QueryLattice,
    *,
    now: float,
    authorized: bool,
    revoked_source_ids: Iterable[str] = (),
    max_results: int = 24,
    max_per_source: int = 3,
    max_per_host: int = 8,
    max_context_chars: int = 14_000,
    reciprocal_rank_k: int = 20,
) -> RetrievalFusion:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(index, EphemeralIndex) or not isinstance(lattice, QueryLattice):
        raise TypeError("typed lattice and source index required")
    if lattice.mandate_digest != mandate.fingerprint or index.mandate_digest != mandate.fingerprint:
        raise PermissionError("cross-campaign retrieval denied")
    integer(max_results, "fusion result limit", 1, 64)
    integer(max_per_source, "fusion source cap", 1, 16)
    integer(max_per_host, "fusion host cap", 1, 32)
    integer(max_context_chars, "fusion text cap", 512, 48_000)
    integer(reciprocal_rank_k, "rank normalization", 1, 100)
    if len(lattice.queries) > 128:
        raise ValueError("query lattice capacity exceeded")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if canonical["snapshot_digest"] != index.source_snapshot_digest:
        raise PermissionError("stale source index")
    revoked = tuple(revoked_source_ids)
    if len(revoked) != len(set(revoked)):
        raise ValueError("duplicate source withdrawal")
    if not set(revoked).issubset(canonical["sources"]):
        raise PermissionError("unknown revoked source")
    # It is intentionally impossible to omit a withdrawal from a constituent
    # query by reusing an older search receipt.
    scores = defaultdict(float)
    rank_by_key = defaultdict(list)
    objectives = defaultdict(set)
    queries = defaultdict(set)
    hits_by_key = {}
    queries_run = 0
    for query_index, query in enumerate(lattice.queries):
        current = search_ephemeral_index(
            mandate, canonical, index, query.query,
            now=now, authorized=authorized, revoked_source_ids=revoked,
            mode="any", limit=32, max_per_source=8,
            required_terms=query.required_terms,
            blocked_terms=query.blocked_terms,
        )
        queries_run += 1
        for rank, hit in enumerate(current.hits, start=1):
            # Required and blocked operator terms are hard passage-level
            # constraints, not mere suggestions for query construction.
            if not passage_matches_operator_terms(
                hit.text, query.required_terms, query.blocked_terms,
            ):
                continue
            key = (hit.source_id, hit.passage_hash, hit.start, hit.end)
            old = hits_by_key.setdefault(key, hit)
            # SearchHit matched_terms and lexical score vary by query;
            # those are *ranking* fields, not anchored passage identity.
            # All source-bound immutable fields must still agree exactly.
            immutable = lambda x: (
                x.source_id, x.canonical_url, x.source_hash,
                x.passage_hash, x.start, x.end, x.text,
            )
            if immutable(old) != immutable(hit):
                raise PermissionError("ambiguous same-key retrieval evidence")
            scores[key] += query.weight / (reciprocal_rank_k + rank)
            rank_by_key[key].append((query_index, rank))
            objectives[key].add(query.objective_id)
            queries[key].add(query.query)
    if len(hits_by_key) > 4096:
        raise ValueError("excessive candidate retrieval universe")
    weighted = []
    for key, hit in hits_by_key.items():
        if not isfinite(scores[key]):
            raise ValueError("nonfinite retrieval score")
        host = urlsplit(hit.canonical_url).hostname
        if not host or host not in mandate.scope.allowed_hosts:
            raise PermissionError("retrieval source outside host grant")
        weighted.append(FusedEvidence(
            source_id=hit.source_id,
            canonical_url=hit.canonical_url,
            source_hash=hit.source_hash,
            passage_hash=hit.passage_hash,
            start=hit.start, end=hit.end,
            text=hit.text,
            score=round(scores[key], 12),
            matched_objective_ids=tuple(sorted(objectives[key])),
            matched_queries=tuple(sorted(queries[key])),
            query_rank_support=tuple(sorted(rank_by_key[key])),
            host=host,
        ))
    weighted.sort(key=lambda row: (-row.score, -len(row.matched_objective_ids),
                                    row.host, row.source_id, row.start, row.end))
    chosen = []
    source_counts = defaultdict(int)
    host_counts = defaultdict(int)
    count_chars = 0
    # Greedy diversification in two passes: first prefer distinct hosts and
    # source identities, then fill residual slots with high-scoring passages.
    for pass_number in (0, 1, 2):
        for row in weighted:
            if row in chosen:
                continue
            if len(chosen) >= max_results:
                break
            if source_counts[row.source_id] >= max_per_source:
                continue
            if host_counts[row.host] >= max_per_host:
                continue
            if pass_number == 0 and host_counts[row.host]:
                continue
            if pass_number == 1 and source_counts[row.source_id]:
                continue
            if count_chars + len(row.text) > max_context_chars:
                continue
            # Defense in depth against forged indexed hits. IndexedSearch
            # performs this check as well, immediately before yielding.
            source = canonical["sources"][row.source_id]
            if (source["content_hash"] != row.source_hash
                    or source["text"][row.start:row.end] != row.text
                    or sha256(row.text.encode("utf-8")).hexdigest() != row.passage_hash):
                raise PermissionError("current fused passage revision mismatch")
            chosen.append(row)
            source_counts[row.source_id] += 1
            host_counts[row.host] += 1
            count_chars += len(row.text)
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "index": index.index_digest,
        "lattice": lattice.lattice_digest,
        "withdrawals": sorted(revoked),
        "result_ids": [
            (x.source_id, x.passage_hash, x.start, x.end, x.score,
             x.matched_objective_ids, x.query_rank_support)
            for x in chosen
        ],
        "limits": (max_results, max_per_source, max_per_host,
                   max_context_chars, reciprocal_rank_k),
    }
    return RetrievalFusion(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        index_digest=index.index_digest, lattice_digest=lattice.lattice_digest,
        excluded_sources=tuple(sorted(revoked)),
        results=tuple(chosen), evaluated_queries=queries_run,
        matched_passages=len(weighted), host_count=len(host_counts),
        total_context_chars=count_chars, fusion_digest=digest(payload),
    )
