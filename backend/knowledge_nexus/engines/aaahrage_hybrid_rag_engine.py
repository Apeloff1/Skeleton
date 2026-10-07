#!/usr/bin/env python3
"""Deterministic in-memory AAAHRAG + hybrid retrieval engine.

The engine keeps a lightweight lexical index for fast local retrieval, supports
one-hop graph expansion for agentic retrieval, and caches immutable result
snapshots between index revisions. External vector/graph stores can replace the
in-memory structures later without changing the public retrieval contract.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import heapq
import math
import re
from typing import Any, Dict, List, Mapping, Sequence


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_VALID_METHODS = frozenset({"combined", "agentic", "hybrid"})


@dataclass
class RetrievalResult:
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]
    retrieval_method: str  # "agentic", "hybrid", or "combined"


class AAAHRAGHybridEngine:
    """Bounded deterministic retrieval for the Knowledge Nexus."""

    def __init__(self) -> None:
        # Public indexes are retained for compatibility with older callers.
        self.vector_index: Dict[str, str] = {}
        self.graph_index: Dict[str, tuple[str, ...]] = {}
        self.keyword_index: Dict[str, tuple[str, ...]] = {}

        self.metadata_index: Dict[str, Dict[str, Any]] = {}
        self._term_counts: Dict[str, Counter[str]] = {}
        self._postings: Dict[str, set[str]] = {}
        self._revision = 0
        self.cache: Dict[tuple[Any, ...], tuple[RetrievalResult, ...]] = {}
        self.usage_stats = {
            "queries": 0,
            "agentic_hits": 0,
            "hybrid_hits": 0,
            "cache_hits": 0,
            "indexed_documents": 0,
        }

    @staticmethod
    def _tokenize(text: str) -> tuple[str, ...]:
        return tuple(match.group(0).lower() for match in _TOKEN_RE.finditer(text))

    @staticmethod
    def _normalize_links(raw_links: Any, *, doc_id: str) -> tuple[str, ...]:
        if isinstance(raw_links, str):
            raw_links = (raw_links,)
        if not isinstance(raw_links, Sequence):
            return ()
        links: list[str] = []
        seen: set[str] = set()
        for value in raw_links:
            if not isinstance(value, str):
                continue
            link = value.strip()
            if not link or link == doc_id or link in seen:
                continue
            seen.add(link)
            links.append(link)
        return tuple(links)

    def retrieve(
        self,
        query: str,
        method: str = "combined",
        top_k: int = 10,
        use_agentic: bool = True,
        use_hybrid: bool = True,
    ) -> List[RetrievalResult]:
        """Retrieve indexed knowledge through hybrid and/or agentic lanes."""

        self.usage_stats["queries"] += 1
        if not isinstance(query, str) or not query.strip():
            return []
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k <= 0:
            return []

        method = str(method).strip().lower()
        if method not in _VALID_METHODS:
            raise ValueError(f"unsupported retrieval method: {method}")

        run_agentic = use_agentic and method in {"combined", "agentic"}
        run_hybrid = use_hybrid and method in {"combined", "hybrid"}
        if not run_agentic and not run_hybrid:
            return []

        normalized_query = " ".join(self._tokenize(query))
        if not normalized_query:
            return []

        cache_key = (
            self._revision,
            normalized_query,
            method,
            top_k,
            run_agentic,
            run_hybrid,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.usage_stats["cache_hits"] += 1
            return list(cached)

        results: list[RetrievalResult] = []
        if run_agentic:
            agentic_results = self._agentic_retrieve(normalized_query, top_k)
            results.extend(agentic_results)
            self.usage_stats["agentic_hits"] += len(agentic_results)

        if run_hybrid:
            hybrid_results = self._hybrid_retrieve(normalized_query, top_k)
            results.extend(hybrid_results)
            self.usage_stats["hybrid_hits"] += len(hybrid_results)

        merged = self._merge_and_rerank(results, top_k)
        self.cache[cache_key] = tuple(merged)
        return merged

    def _candidate_ids(self, query_tokens: Sequence[str]) -> set[str]:
        candidates: set[str] = set()
        for token in set(query_tokens):
            candidates.update(self._postings.get(token, ()))
        return candidates

    def _score_document(
        self,
        query_tokens: Sequence[str],
        query_counts: Counter[str],
        doc_id: str,
    ) -> tuple[float, tuple[str, ...]]:
        doc_counts = self._term_counts[doc_id]
        document_count = max(len(self.vector_index), 1)
        weighted_matches = 0.0
        weighted_query = 0.0
        matched_terms: list[str] = []

        for token, query_count in query_counts.items():
            document_frequency = len(self._postings.get(token, ()))
            idf = math.log((document_count + 1.0) / (document_frequency + 1.0)) + 1.0
            weighted_query += query_count * idf
            doc_count = doc_counts.get(token, 0)
            if not doc_count:
                continue
            matched_terms.append(token)
            weighted_matches += min(query_count, doc_count) * idf

        if not weighted_matches or not weighted_query:
            return 0.0, ()

        coverage = weighted_matches / weighted_query
        phrase = " ".join(query_tokens)
        phrase_bonus = 1.0 if phrase and phrase in self.vector_index[doc_id].lower() else 0.0
        score = min(1.0, 0.85 * coverage + 0.15 * phrase_bonus)
        return score, tuple(matched_terms)

    def _result(
        self,
        doc_id: str,
        score: float,
        *,
        method: str,
        extra_metadata: Mapping[str, Any] | None = None,
    ) -> RetrievalResult:
        metadata = dict(self.metadata_index.get(doc_id, {}))
        metadata["doc_id"] = doc_id
        if extra_metadata:
            metadata.update(extra_metadata)
        return RetrievalResult(
            content=self.vector_index[doc_id],
            source=str(metadata.get("source") or doc_id),
            score=score,
            metadata=metadata,
            retrieval_method=method,
        )

    def _hybrid_retrieve(self, query: str, top_k: int) -> List[RetrievalResult]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        candidates = self._candidate_ids(query_tokens)
        if not candidates:
            return []

        query_counts: Counter[str] = Counter(query_tokens)
        scored: list[RetrievalResult] = []
        for doc_id in candidates:
            score, matched_terms = self._score_document(query_tokens, query_counts, doc_id)
            if score <= 0.0:
                continue
            scored.append(
                self._result(
                    doc_id,
                    score,
                    method="hybrid",
                    extra_metadata={"matched_terms": matched_terms},
                )
            )

        return heapq.nlargest(top_k, scored, key=lambda row: (row.score, row.source))

    def _agentic_retrieve(self, query: str, top_k: int) -> List[RetrievalResult]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        seed_limit = min(max(top_k * 2, 4), 64)
        seeds = self._hybrid_retrieve(query, seed_limit)
        if not seeds:
            return []

        query_counts: Counter[str] = Counter(query_tokens)
        by_doc: dict[str, RetrievalResult] = {}

        for seed in seeds:
            seed_id = str(seed.metadata["doc_id"])
            by_doc[seed_id] = self._result(
                seed_id,
                seed.score,
                method="agentic",
                extra_metadata={
                    "matched_terms": seed.metadata.get("matched_terms", ()),
                    "graph_hop": 0,
                },
            )

            for linked_id in self.graph_index.get(seed_id, ()):
                if linked_id not in self.vector_index:
                    continue
                direct_score, matched_terms = self._score_document(
                    query_tokens, query_counts, linked_id
                )
                linked_score = min(1.0, 0.65 * seed.score + 0.35 * direct_score)
                linked = self._result(
                    linked_id,
                    linked_score,
                    method="agentic",
                    extra_metadata={
                        "matched_terms": matched_terms,
                        "graph_hop": 1,
                        "via": seed_id,
                    },
                )
                existing = by_doc.get(linked_id)
                if existing is None or linked.score > existing.score:
                    by_doc[linked_id] = linked

        return heapq.nlargest(
            top_k,
            by_doc.values(),
            key=lambda row: (row.score, row.source),
        )

    @staticmethod
    def _merge_and_rerank(
        results: List[RetrievalResult],
        top_k: int,
    ) -> List[RetrievalResult]:
        best: dict[str, tuple[int, RetrievalResult]] = {}
        for index, result in enumerate(results):
            doc_id = str(result.metadata.get("doc_id") or "")
            key = doc_id or f"{result.source}\x1f{result.content}"
            current = best.get(key)
            if current is None or result.score > current[1].score:
                best[key] = (index, result)

        ranked = heapq.nlargest(
            top_k,
            best.values(),
            key=lambda item: (item[1].score, -item[0]),
        )
        return [result for _, result in ranked]

    def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Index or replace a document and atomically invalidate cached retrieval."""

        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ValueError("doc_id must be non-empty text")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be non-empty text")

        doc_id = doc_id.strip()
        metadata_copy = dict(metadata or {})

        old_tokens = self.keyword_index.get(doc_id, ())
        for token in set(old_tokens):
            postings = self._postings.get(token)
            if postings is None:
                continue
            postings.discard(doc_id)
            if not postings:
                del self._postings[token]

        tokens = self._tokenize(content)
        counts: Counter[str] = Counter(tokens)
        for token in counts:
            self._postings.setdefault(token, set()).add(doc_id)

        self.vector_index[doc_id] = content
        self.keyword_index[doc_id] = tokens
        self._term_counts[doc_id] = counts
        self.metadata_index[doc_id] = metadata_copy
        self.graph_index[doc_id] = self._normalize_links(
            metadata_copy.get("links", ()), doc_id=doc_id
        )

        self._revision += 1
        self.cache.clear()
        self.usage_stats["indexed_documents"] = len(self.vector_index)


# Singleton instance for system-wide use
aaahrage_engine = AAAHRAGHybridEngine()
