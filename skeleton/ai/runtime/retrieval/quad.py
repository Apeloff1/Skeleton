"""
Skeleton Retrieval — Quad-plane retriever (RAG+CAG+MAG+KAG)

Provides:
- QuadRetriever: Unified retrieval across four memory planes
- PlaneResult: Results from a single plane

Ingestion feeds RAG with chunks AND the KAG plane with triples
extracted from the text, so the knowledge graph self-populates.
"""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Event, RLock
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import EventBus
from skeleton.retrieval.cache import ResultCache
from skeleton.retrieval.extraction import TripleExtractor
from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult


@dataclass
class PlaneResult:
    """Results from a single retrieval plane."""

    plane: str
    results: List[ScoredResult]
    latency_ms: float = 0.0
    from_cache: bool = False


class QuadRetriever:
    """Unified retrieval across RAG, CAG, MAG, and KAG planes.

    The four-plane architecture:
    - RAG (Retrieval-Augmented Generation): dense vector retrieval
    - CAG (Context-Augmented Generation): contextual associative memory
    - MAG (Multi-Agent Generation): episodic agent memory
    - KAG (Knowledge-Augmented Generation): structured knowledge graph

    Registered planes execute concurrently. Results are collected in registration
    order so equal-score fusion ties remain deterministic even when faster planes
    finish first. Identical cacheable misses are coalesced so concurrent callers
    share one plane fan-out instead of stampeding the same backends.
    """

    _PLANE_HISTORY_LIMIT = 64
    _MAX_PARALLEL_PLANES = 4

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        extractor: Optional[TripleExtractor] = None,
        cache: Optional[ResultCache] = None,
    ) -> None:
        self._bus = bus
        self._planes: Dict[str, Any] = {}
        self._fuser = Fuser(strategy=FusionStrategy.RRF)
        self._cache = cache if cache is not None else ResultCache()
        self._extractor = extractor or TripleExtractor()
        self._plane_history: deque[str] = deque(maxlen=self._PLANE_HISTORY_LIMIT)
        self._state_lock = RLock()
        self._cache_generation = 0
        self._inflight: Dict[str, Event] = {}
        self._stats = {
            "queries": 0,
            "cache_hits": 0,
            "coalesced_queries": 0,
            "plane_failures": 0,
            "ingested": 0,
            "triples_extracted": 0,
        }

    def register_plane(self, name: str, retriever: Any) -> None:
        """Register or replace a retrieval plane and invalidate cached rankings."""
        if retriever is None:
            return
        with self._state_lock:
            self._planes[name] = retriever
            self._cache_generation += 1
            self._cache.clear()

    def as_retriever(
        self,
        *,
        k: int = 8,
        use_cache: bool = True,
    ) -> Callable[[str], List[ScoredResult]]:
        """Return a single-argument adapter suitable for ``QueryPlanner.register``."""

        def _retrieve(query: str) -> List[ScoredResult]:
            return self.retrieve(query, k=k, use_cache=use_cache)

        return _retrieve

    @staticmethod
    def _metadata_provenance(metadata: Dict[str, Any]) -> str:
        explicit = metadata.get("provenance")
        if isinstance(explicit, str) and explicit:
            return explicit
        repository = metadata.get("source_repository")
        revision = metadata.get("source_revision")
        path = metadata.get("source_path")
        if not any(isinstance(value, str) and value for value in (repository, revision, path)):
            return ""
        source = str(repository or "unknown")
        if revision:
            source += f"@{revision}"
        if path:
            source += f":{path}"
        return source

    @classmethod
    def _normalize_result(cls, plane_name: str, result: Any) -> Optional[ScoredResult]:
        """Normalize plane-native results into the fusion contract.

        Memory stores return ``ScoredChunk`` while retrieval-native planes return
        ``ScoredResult``. Crossing that boundary without normalization leaves the
        fuser looking for ``fragment_id``/``content`` on a ``ScoredChunk`` and
        breaks API retrieval after successful ingestion.

        Existing ``ScoredResult`` instances are never mutated. A plane correction
        returns a shallow dataclass copy so callers can safely reuse their result.
        """
        if isinstance(result, ScoredResult):
            if result.plane in (None, "", "rag") and plane_name != "rag":
                return replace(result, plane=plane_name)
            return result

        chunk = getattr(result, "chunk", None)
        if chunk is not None:
            fragment_id = str(getattr(chunk, "chunk_id", "") or "")
            content = str(getattr(chunk, "text", "") or "")
            if not fragment_id:
                return None
            raw_metadata = getattr(chunk, "metadata", {}) or {}
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            return ScoredResult(
                fragment_id=fragment_id,
                content=content,
                score=float(getattr(result, "score", 0.0)),
                plane=str(getattr(result, "plane", "") or plane_name),
                provenance=str(
                    getattr(result, "provenance", "")
                    or cls._metadata_provenance(metadata)
                ),
                metadata=metadata,
            )

        if isinstance(result, dict):
            fragment_id = result.get("fragment_id") or result.get("id") or result.get("key")
            if not fragment_id:
                return None
            content = result.get("content") or result.get("text") or result.get("value") or ""
            raw_metadata = result.get("metadata") or {}
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            return ScoredResult(
                fragment_id=str(fragment_id),
                content=str(content),
                score=float(result.get("score", 0.0)),
                plane=str(result.get("plane") or plane_name),
                provenance=str(
                    result.get("provenance") or cls._metadata_provenance(metadata)
                ),
                metadata=metadata,
            )

        return None

    def _query_plane(
        self,
        plane_name: str,
        retriever: Any,
        query: str,
        k: int,
    ) -> List[ScoredResult]:
        """Execute one plane and normalize its native result objects."""
        if hasattr(retriever, "query"):
            if plane_name == "cag":
                plane_results = retriever.query(query)
            else:
                plane_results = retriever.query(query, top_k=k)
        elif hasattr(retriever, "retrieve"):
            plane_results = retriever.retrieve(query, k=k)
        else:
            return []

        return [
            item
            for raw in plane_results
            if (item := self._normalize_result(plane_name, raw)) is not None
        ]

    def _emit_cache_hit(self, query: str, hits: int) -> None:
        if self._bus:
            self._bus.emit("retrieval.cache_hit", {"query": query, "hits": hits})

    def _finish_inflight(self, cache_key: str, flight: Event) -> None:
        """Release waiters for a cache key without disturbing a newer flight."""
        with self._state_lock:
            if self._inflight.get(cache_key) is flight:
                self._inflight.pop(cache_key, None)
            flight.set()

    def retrieve(self, query: str, k: int = 8, use_cache: bool = True) -> List[ScoredResult]:
        """Query registered planes concurrently and fuse deterministic results."""
        t0 = time.perf_counter()
        with self._state_lock:
            generation = self._cache_generation
            plane_items = tuple(self._planes.items())

        cache_key = f"{generation}:{k}:{query}"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                with self._state_lock:
                    self._stats["cache_hits"] += 1
                self._emit_cache_hit(query, len(cached))
                return list(cached)

        with self._state_lock:
            self._stats["queries"] += 1
            flight = self._inflight.get(cache_key) if use_cache else None
            owns_flight = use_cache and flight is None
            if owns_flight:
                flight = Event()
                self._inflight[cache_key] = flight
            elif flight is not None:
                self._stats["coalesced_queries"] += 1

        if use_cache and not owns_flight:
            assert flight is not None
            flight.wait()
            cached = self._cache.get(cache_key)
            if cached is not None:
                with self._state_lock:
                    self._stats["cache_hits"] += 1
                self._emit_cache_hit(query, len(cached))
                return list(cached)

            # A topology/ingestion generation change can intentionally prevent
            # the leader from caching its old-generation result. Retry against
            # the current generation rather than serving that stale snapshot.
            return self.retrieve(query, k=k, use_cache=True)

        try:
            if use_cache:
                # Close the handoff race where a previous flight populated the
                # cache after our first miss but before this caller became leader.
                cached = self._cache.get(cache_key)
                if cached is not None:
                    with self._state_lock:
                        self._stats["cache_hits"] += 1
                    self._emit_cache_hit(query, len(cached))
                    return list(cached)

            results_by_plane: Dict[str, List[ScoredResult]] = {}
            failures: List[str] = []

            if len(plane_items) == 1:
                plane_name, retriever = plane_items[0]
                try:
                    normalized = self._query_plane(plane_name, retriever, query, k)
                except Exception:
                    failures.append(plane_name)
                else:
                    if normalized:
                        results_by_plane[plane_name] = normalized
            elif plane_items:
                with ThreadPoolExecutor(
                    max_workers=min(len(plane_items), self._MAX_PARALLEL_PLANES),
                    thread_name_prefix="skeleton-retrieval",
                ) as executor:
                    futures = [
                        (
                            plane_name,
                            executor.submit(
                                self._query_plane,
                                plane_name,
                                retriever,
                                query,
                                k,
                            ),
                        )
                        for plane_name, retriever in plane_items
                    ]

                    # Consume in registration order, not completion order. The work
                    # still overlaps, while RRF tie ordering stays deterministic.
                    for plane_name, future in futures:
                        try:
                            normalized = future.result()
                        except Exception:
                            failures.append(plane_name)
                            continue
                        if normalized:
                            results_by_plane[plane_name] = normalized

            with self._state_lock:
                self._stats["plane_failures"] += len(failures)
                for plane_name in results_by_plane:
                    self._plane_history.append(plane_name)

            fused = self._fuser.fuse(results_by_plane, top_k=k)

            # Generation checking closes a subtle invalidation race: a query that
            # started before register_plane()/ingest_document() may finish after the
            # cache was cleared. It must not repopulate that cache with stale results.
            if use_cache:
                with self._state_lock:
                    if generation == self._cache_generation:
                        self._cache.put(cache_key, tuple(fused))

            if self._bus:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self._bus.emit(
                    "retrieval.completed",
                    {
                        "query": query,
                        "results": len(fused),
                        "elapsed_ms": round(elapsed_ms, 3),
                        "planes": {plane: len(hits) for plane, hits in results_by_plane.items()},
                    },
                )
                self._bus.emit(
                    "retrieval.quad.query",
                    {
                        "query": query,
                        "planes": list(results_by_plane.keys()),
                        "failed_planes": list(failures),
                        "results": len(fused),
                    },
                )

            return fused
        finally:
            if use_cache and owns_flight and flight is not None:
                self._finish_inflight(cache_key, flight)

    def ingest_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        salience: float = 0.5,
    ) -> int:
        """Ingest a document: chunk into RAG and extract triples into KAG.

        Returns the number of chunks ingested into RAG. Cache generations are
        advanced before and after mutation so neither pre-ingest nor partially
        ingested results can survive as reusable cached rankings.
        """
        with self._state_lock:
            rag = self._planes.get("rag")
            kag = self._planes.get("kag")
            mag = self._planes.get("mag")
            self._cache_generation += 1
            self._cache.clear()

        chunks = 0
        triples_extracted = 0

        if rag and hasattr(rag, "add"):
            from skeleton.memory.core import Chunk

            chunk = Chunk(text=text, chunk_id=doc_id, metadata=metadata or {})
            rag.add(chunk)
            chunks += 1

        # Self-populate the KAG plane from the same text.
        if kag is not None and hasattr(kag, "graph"):
            triples = self._extractor.extract(text)
            for subject, predicate, obj in triples:
                kag.graph.add(subject, predicate, obj)
            triples_extracted = len(triples)

        # MAG episodic trace for high-salience documents.
        if mag is not None and hasattr(mag, "record") and salience >= 0.7:
            mag.record(doc_id, text[:500], tags=(metadata or {}).get("tags", []))

        with self._state_lock:
            self._stats["triples_extracted"] += triples_extracted
            self._stats["ingested"] += chunks
            self._cache_generation += 1
            self._cache.clear()
            total_triples = self._stats["triples_extracted"]

        if self._bus:
            self._bus.emit(
                "retrieval.ingested",
                {"doc_id": doc_id, "chunks": chunks},
            )
            self._bus.emit(
                "retrieval.quad.ingested",
                {
                    "doc_id": doc_id,
                    "chunks": chunks,
                    "triples": total_triples,
                    "salience": salience,
                },
            )

        return chunks

    def ingest_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        provenance: str = "",
    ) -> None:
        """Insert one structured triple into KAG (lazy-register the plane)."""

        from skeleton.retrieval.kag import validate_fact_confidence

        confidence = validate_fact_confidence(confidence)
        if not isinstance(provenance, str):
            raise TypeError("provenance must be a string")

        with self._state_lock:
            kag = self._planes.get("kag")
            if kag is None:
                from skeleton.retrieval.kag import KAGRetriever

                kag = KAGRetriever()
                self._planes["kag"] = kag
            self._cache_generation += 1
            self._cache.clear()

        added = 0
        if hasattr(kag, "graph"):
            kag.graph.add(
                subject,
                predicate,
                obj,
                confidence=confidence,
                provenance=provenance,
            )
            added = 1

        with self._state_lock:
            if added:
                self._stats["triples_extracted"] += added
            self._cache_generation += 1
            self._cache.clear()

    def stats(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                **self._stats,
                "planes_used": list(self._plane_history),
                "planes_registered": len(self._planes),
                "cache_size": self._cache.size(),
                "cache_generation": self._cache_generation,
            }
