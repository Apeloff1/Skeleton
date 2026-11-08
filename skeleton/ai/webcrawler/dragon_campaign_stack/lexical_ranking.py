"""Bounded BM25/phrase-proximity ranker over current Dragon source snapshots.

This is a genuinely different lexical retrieval algorithm from reciprocal-rank
fusion: passage-level document frequencies, explicit TF saturation, bounded
query-term proximity, and host/source-fair result selection. It only consumes
passages from the existing current-source ephemeral index. No model provider,
embedding service, internet request, training, public knowledge promotion,
or new persistent search engine is involved.

The index is completely rebuilt and compared to its original receipt at
its own recorded clock before ranking. This prevents a constructed index
from supplying fabricated terms, spans, source IDs or digest identities.
All selected hits are still unreviewed external evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from math import log, isfinite
from typing import Iterable
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite, integer
from .policy_matrix import SourcePolicyProjection
from .query_lattice import (
    QueryLattice, QueryVariant, passage_matches_operator_terms,
)
from .retrieval_fusion import FusedEvidence, RetrievalFusion
from .source_index import EphemeralIndex, IndexedPassage, build_ephemeral_index, _terms


@dataclass(frozen=True)
class LexicalRankingWeights:
    k1: float = 1.2
    length_b: float = 0.75
    bm25_weight: float = 0.72
    query_coverage_weight: float = 0.18
    phrase_proximity_weight: float = 0.10
    missing_term_penalty: float = 0.45

    def __post_init__(self):
        finite(self.k1, "BM25 term saturation", 0.1, 3)
        finite(self.length_b, "BM25 document length weight", 0, 1)
        for key in ("bm25_weight", "query_coverage_weight",
                    "phrase_proximity_weight", "missing_term_penalty"):
            finite(getattr(self, key), key, 0, 1)
        if abs(sum((self.bm25_weight, self.query_coverage_weight,
                    self.phrase_proximity_weight)) - 1.0) > 1e-9:
            raise ValueError("lexical scoring components must sum to one")


@dataclass(frozen=True)
class PassageScore:
    source_id: str
    passage_hash: str
    start: int
    end: int
    bm25: float
    query_coverage: float
    phrase_proximity: float
    query_weight: float
    combined: float
    matched_terms: tuple[str, ...]
    objective_id: str
    query_index: int
    model_probability: bool = False


@dataclass(frozen=True)
class LexicalRankingReport:
    mandate_digest: str
    source_snapshot_digest: str
    index_digest: str
    lattice_digest: str
    policy_digest: str
    weights: LexicalRankingWeights
    document_count: int
    indexed_term_count: int
    evaluated_queries: int
    scored_passages: int
    considered_candidates: int
    scored_receipts: tuple[PassageScore, ...]
    selected: tuple[FusedEvidence, ...]
    excluded_sources: tuple[str, ...]
    context_chars: int
    ranking_digest: str
    ai_embedding_used: bool = False
    factual_confidence_calibrated: bool = False
    remote_network_used: bool = False
    knowledge_promoted: bool = False


def _windows(tokens: tuple[str, ...], query: tuple[str, ...]) -> float:
    """Longest proximity score from the minimum interval covering all terms.

    Sliding window is O(len(tokens)): a bounded document of <= 600 Unicode
    chars cannot exhaust the kernel with adversarial repetitive terms.
    """
    target = set(query)
    if not target or not target.issubset(tokens):
        return 0.0
    count = Counter()
    missing = len(target)
    left = 0
    best = len(tokens) + 1
    for right, term in enumerate(tokens):
        if term in target:
            if count[term] == 0:
                missing -= 1
            count[term] += 1
        while not missing and left <= right:
            best = min(best, right - left + 1)
            old = tokens[left]
            if old in target:
                count[old] -= 1
                if count[old] == 0:
                    missing += 1
            left += 1
    return round(len(target) / max(best, len(target)), 8)


def _score_query(
    passage: IndexedPassage,
    words: tuple[str, ...],
    variant: QueryVariant,
    document_frequency: dict[str, int],
    total_docs: int,
    average_length: float,
    weights: LexicalRankingWeights,
    query_index: int,
) -> PassageScore | None:
    tokens = tuple(dict.fromkeys(variant.terms))
    term_freq = Counter(words)
    present = tuple(sorted(x for x in tokens if term_freq.get(x, 0) > 0))
    if not present:
        return None
    length_norm = 1 - weights.length_b + weights.length_b * (
        len(words) / max(1.0, average_length)
    )
    bm25 = 0.0
    for word in tokens:
        count = term_freq.get(word, 0)
        if not count:
            continue
        df = document_frequency.get(word, 0)
        idf = log(1 + (total_docs - df + .5) / (df + .5))
        bm25 += idf * (count * (weights.k1 + 1)) / (
            count + weights.k1 * length_norm
        )
    coverage = len(present) / len(tokens)
    proximity = _windows(words, tokens)
    # Saturation limits extreme lexical repetition to a finite interval.
    saturated_bm25 = bm25 / (1.0 + bm25)
    penalty = 1 - weights.missing_term_penalty * (1 - coverage)
    combined = (
        weights.bm25_weight * saturated_bm25
        + weights.query_coverage_weight * coverage
        + weights.phrase_proximity_weight * proximity
    ) * variant.weight * penalty
    if not isfinite(combined) or combined < 0:
        raise ValueError("nonfinite lexical rank score")
    return PassageScore(
        source_id=passage.source_id, passage_hash=passage.passage_hash,
        start=passage.start, end=passage.end,
        bm25=round(bm25, 10),
        query_coverage=round(coverage, 8),
        phrase_proximity=proximity,
        query_weight=variant.weight,
        combined=round(combined, 12),
        matched_terms=present,
        objective_id=variant.objective_id,
        query_index=query_index,
    )


def rank_ephemeral_research(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    index: EphemeralIndex,
    lattice: QueryLattice,
    *,
    now: float,
    authorized: bool,
    weights: LexicalRankingWeights = LexicalRankingWeights(),
    max_results: int = 16,
    max_per_source: int = 3,
    max_per_host: int = 8,
    max_context_chars: int = 8000,
    max_receipts: int = 1024,
) -> LexicalRankingReport:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_results, "lexical results", 1, 32)
    integer(max_per_source, "lexical per-source results", 1, 8)
    integer(max_per_host, "lexical per-host results", 1, 16)
    integer(max_context_chars, "lexical context chars", 512, 24_000)
    integer(max_receipts, "lexical score trace capacity", 1, 8192)
    if not isinstance(weights, LexicalRankingWeights):
        raise TypeError("typed lexical scoring weights required")
    if any(x != mandate.fingerprint for x in (
        policy.mandate_digest, index.mandate_digest, lattice.mandate_digest
    )):
        raise PermissionError("cross-campaign BM25 retrieval")
    current = CrawlRun.from_snapshot(snapshot).snapshot()
    if index.source_snapshot_digest != current["snapshot_digest"] or (
        policy.source_snapshot_digest != current["snapshot_digest"]
    ):
        raise PermissionError("BM25 index or policy revision stale")
    if index.created_at > now:
        raise ValueError("future-dated lexical index")
    if set(policy.allowed_source_ids) | set(policy.excluded_source_ids) != set(
        current["sources"]
    ):
        raise PermissionError("incomplete BM25 source policy")
    if set(policy.allowed_source_ids) & set(policy.excluded_source_ids):
        raise PermissionError("ambiguous source policy eligibility")
    # Rebuild and byte-for-byte verify the entire index from canonical
    # source snapshots, including its source classifications and exact spans.
    current_index = build_ephemeral_index(
        mandate, current, now=index.created_at, authorized=True,
        revoked_source_ids=policy.excluded_source_ids,
        max_passages=max(1, len(index.passages)),
    )
    if current_index != index:
        raise PermissionError("BM25 cannot trust a forged or stale index receipt")
    if len(lattice.queries) > 128 or not lattice.queries:
        raise ValueError("finite operator query lattice required")
    if any(
        row.query != " ".join(row.terms)
        or not row.objective_id or not row.retrieval_only
        for row in lattice.queries
    ):
        raise ValueError("unbound or unauthorized lexical query variant")
    documents = []
    all_words = []
    df = defaultdict(int)
    sources = current["sources"]
    for passage in index.passages:
        if passage.source_id not in policy.allowed_source_ids:
            raise PermissionError("policy-held source in lexical candidate universe")
        if passage.source_id not in sources:
            raise PermissionError("unknown lexical source")
        if sources[passage.source_id]["text"][passage.start:passage.end] != passage.text:
            raise PermissionError("lexical passage source text changed")
        if len(passage.text) > 600:
            raise ValueError("lexical passage exceeds bounded segmentation")
        words = _terms(passage.text)
        documents.append(passage)
        all_words.append(words)
        for term in set(words):
            df[term] += 1
    count = len(documents)
    average_length = sum(len(words) for words in all_words) / count if count else 1.0
    ranked = defaultdict(list)
    receipt_count = 0
    for query_index, query in enumerate(lattice.queries):
        if not isinstance(query, QueryVariant):
            raise TypeError("typed query lattice row required")
        if len(query.terms) > 16:
            raise ValueError("too many query expansion terms")
        for passage, words in zip(documents, all_words):
            if not passage_matches_operator_terms(
                passage.text, query.required_terms, query.blocked_terms,
            ):
                continue
            receipt = _score_query(
                passage, words, query, df, max(1, count),
                average_length, weights, query_index,
            )
            if receipt is None:
                continue
            receipt_count += 1
            if receipt_count > max_receipts:
                raise ValueError("lexical scoring trace capacity exceeded")
            key = passage.source_id, passage.passage_hash, passage.start, passage.end
            ranked[key].append(receipt)
    # Record actual within-query ranks. A rank of one is never asserted for
    # every passage: each query's candidate set has a deterministic order.
    rank_lookup = {}
    rows_by_query = defaultdict(list)
    for key, receipts in ranked.items():
        for receipt in receipts:
            rows_by_query[receipt.query_index].append((key, receipt))
    for query_index, rows in rows_by_query.items():
        rows.sort(key=lambda item: (
            -item[1].combined, item[1].source_id, item[1].start,
            item[1].end,
        ))
        for rank, (key, _) in enumerate(rows, 1):
            rank_lookup[(query_index, key)] = rank
    # A query may target the same passage repeatedly; identity still maps to
    # one external source and is never counted as independent corroboration.
    by_key = {
        (p.source_id, p.passage_hash, p.start, p.end): p
        for p in documents
    }
    candidate = []
    for key, receipts in ranked.items():
        passage = by_key[key]
        source = sources[passage.source_id]
        host = urlsplit(passage.canonical_url).hostname
        if not host or host not in mandate.scope.allowed_hosts:
            raise PermissionError("lexical result escaped canonical host grant")
        # Saturate multi-query agreement instead of allowing many redundant
        # variants to amplify the same web page into apparent certainty.
        score = 1.0
        for row in receipts:
            score *= 1 - min(1.0, row.combined)
        score = round(1 - score, 12)
        # Each exact query receipt can be located again using its operator-
        # authored variant ordinal and local score; no model claim is used.
        matching = tuple(sorted({x.objective_id for x in receipts}))
        queries = tuple(sorted({lattice.queries[x.query_index].query for x in receipts}))
        traces = tuple(sorted((x.query_index, rank_lookup[(x.query_index, key)]) for x in receipts))
        candidate.append(FusedEvidence(
            source_id=passage.source_id,
            canonical_url=passage.canonical_url,
            source_hash=passage.full_content_hash,
            passage_hash=passage.passage_hash,
            start=passage.start, end=passage.end,
            text=passage.text, score=score,
            matched_objective_ids=matching,
            matched_queries=queries, query_rank_support=traces,
            host=host,
        ))
    candidate.sort(key=lambda x: (-x.score, -len(x.matched_objective_ids),
                                  x.host, x.source_id, x.start, x.end))
    chosen = []
    per_source = Counter()
    per_host = Counter()
    occupied = set()
    total_chars = 0
    for stage in range(3):
        for hit in candidate:
            key = hit.source_id, hit.passage_hash, hit.start, hit.end
            if key in occupied:
                continue
            if len(chosen) >= max_results:
                break
            if stage == 0 and per_host[hit.host]:
                continue
            if stage == 1 and per_source[hit.source_id]:
                continue
            if per_source[hit.source_id] >= max_per_source:
                continue
            if per_host[hit.host] >= max_per_host:
                continue
            if total_chars + len(hit.text) > max_context_chars:
                continue
            chosen.append(hit)
            occupied.add(key)
            per_source[hit.source_id] += 1
            per_host[hit.host] += 1
            total_chars += len(hit.text)
    flat = [row for refs in ranked.values() for row in refs]
    flat.sort(key=lambda x: (x.query_index, -x.combined,
                             x.source_id, x.start, x.end))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": current["snapshot_digest"],
        "policy": policy.policy_digest,
        "index": index.index_digest, "lattice": lattice.lattice_digest,
        "weights": asdict(weights),
        "scores": [asdict(x) for x in flat],
        "selected": [(x.source_id, x.passage_hash, x.start, x.end,
                      x.score, x.matched_objective_ids) for x in chosen],
        "limits": (max_results, max_per_source, max_per_host,
                   max_context_chars, max_receipts),
    }
    return LexicalRankingReport(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=current["snapshot_digest"],
        index_digest=index.index_digest, lattice_digest=lattice.lattice_digest,
        policy_digest=policy.policy_digest, weights=weights,
        document_count=count, indexed_term_count=len(df),
        evaluated_queries=len(lattice.queries),
        scored_passages=len(ranked), considered_candidates=len(candidate),
        scored_receipts=tuple(flat), selected=tuple(chosen),
        excluded_sources=policy.excluded_source_ids,
        context_chars=total_chars, ranking_digest=digest(payload),
    )


def lexical_report_to_fusion(report: LexicalRankingReport) -> RetrievalFusion:
    """Convert a current lexical ranking receipt into the existing downstream API.

    This bridge is a read-only adapter. Downstream source, context, graph and
    citation gates still inspect the exact original canonical crawl snapshot.
    """
    if not isinstance(report, LexicalRankingReport):
        raise TypeError("typed lexical ranking receipt required")
    if report.ai_embedding_used or report.remote_network_used or report.knowledge_promoted:
        raise PermissionError("lexical adapter cannot claim external authority")
    return RetrievalFusion(
        mandate_digest=report.mandate_digest,
        source_snapshot_digest=report.source_snapshot_digest,
        index_digest=report.index_digest, lattice_digest=report.lattice_digest,
        excluded_sources=report.excluded_sources,
        results=report.selected, evaluated_queries=report.evaluated_queries,
        matched_passages=report.scored_passages,
        host_count=len({x.host for x in report.selected}),
        total_context_chars=report.context_chars,
        fusion_digest=digest({
            "mode": "lexical_bm25_proximity_v1",
            "ranking": report.ranking_digest,
            "ids": [(x.source_id, x.passage_hash, x.start, x.end)
                    for x in report.selected],
        }),
    )
