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
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from skeleton.kernel.events import EventBus
from skeleton.retrieval.cache import ResultCache
from skeleton.retrieval.extraction import TripleExtractor
from skeleton.retrieval.freshness import FreshnessRegistry
from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult
from skeleton.retrieval.receipts import (
    ReceiptLedger,
    RetrievalReceipt,
    query_digest,
    receipt_id,
)
from skeleton.retrieval.scope import RetrievalScope, ScopedRetrievalError


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
    _RETRIEVAL_STATE_VERSION = 1

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        extractor: Optional[TripleExtractor] = None,
        cache: Optional[ResultCache] = None,
        freshness: Optional[FreshnessRegistry] = None,
        *,
        receipt_limit: int = 256,
    ) -> None:
        self._bus = bus
        self._planes: Dict[str, Any] = {}
        self._fuser = Fuser(strategy=FusionStrategy.RRF)
        self._cache = cache if cache is not None else ResultCache()
        self._extractor = extractor or TripleExtractor()
        self._freshness = freshness if freshness is not None else FreshnessRegistry()
        self._receipts = ReceiptLedger(max_entries=receipt_limit)
        self._receipt_sequence = 0
        self._plane_history: deque[str] = deque(maxlen=self._PLANE_HISTORY_LIMIT)
        self._state_lock = RLock()
        self._cache_generation = 0
        self._inflight: Dict[str, Event] = {}
        self._weight_learner = None
        self._static_weights = {"rag": 1.0, "cag": 0.8, "mag": 0.7, "kag": 0.9}
        self._stats = {
            "queries": 0,
            "cache_hits": 0,
            "coalesced_queries": 0,
            "plane_failures": 0,
            "partial_queries": 0,
            "receipts_created": 0,
            "feedback_consumed": 0,
            "stale_results": 0,
            "ingested": 0,
            "triples_extracted": 0,
        }

    def register_plane(self, name: str, retriever: Any) -> None:
        """Register or replace a retrieval plane and invalidate cached rankings."""
        if retriever is None:
            return
        with self._state_lock:
            self._planes[name] = retriever
            self._invalidate_cache_locked()

    def mark_plane_freshness(
        self,
        name: str,
        *,
        index_version: str,
        source_revision: str,
        indexed_at: Optional[float] = None,
        stale_after_s: float = 300.0,
    ) -> Dict[str, Any]:
        """Publish projection freshness and invalidate rankings carrying old metadata."""
        state = self._freshness.update(
            name,
            index_version=index_version,
            source_revision=source_revision,
            indexed_at=indexed_at,
            stale_after_s=stale_after_s,
        )
        with self._state_lock:
            self._invalidate_cache_locked()
        metadata = self._freshness.metadata(name)
        if metadata is None:
            raise RuntimeError("freshness state disappeared after update")
        return metadata

    def freshness_snapshot(self) -> Dict[str, Any]:
        return self._freshness.snapshot()

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
            fragment_id = str(
                getattr(chunk, "chunk_id", "")
                or getattr(chunk, "id", "")
                or ""
            )
            content = str(getattr(chunk, "text", "") or "")
            if not fragment_id:
                return None
            raw_metadata = getattr(chunk, "metadata", {}) or {}
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            native_plane = (
                getattr(result, "plane", "")
                or getattr(chunk, "source_tier", "")
                or plane_name
            )
            return ScoredResult(
                fragment_id=fragment_id,
                content=content,
                score=float(getattr(result, "score", 0.0)),
                plane=str(native_plane),
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
        scope: Optional[RetrievalScope] = None,
    ) -> List[ScoredResult]:
        """Execute one plane and normalize its native result objects."""
        if scope is not None:
            scoped = getattr(retriever, "query_scoped", None)
            if not callable(scoped):
                raise ScopedRetrievalError(
                    f"retrieval plane {plane_name!r} cannot enforce pre-ranking scope"
                )
            plane_results = scoped(
                query,
                top_k=k,
                scope=scope.to_dict(),
            )
        elif hasattr(retriever, "query"):
            if plane_name == "cag":
                plane_results = retriever.query(query)
            else:
                plane_results = retriever.query(query, top_k=k)
        elif hasattr(retriever, "retrieve"):
            plane_results = retriever.retrieve(query, k=k)
        else:
            return []

        normalized = [
            item
            for raw in plane_results
            if (item := self._normalize_result(plane_name, raw)) is not None
        ]
        freshness = self._freshness.metadata(plane_name)
        for item in normalized:
            metadata = dict(item.metadata)
            metadata["index_freshness"] = (
                {"tracked": False, "stale": None}
                if freshness is None
                else {"tracked": True, **freshness}
            )
            item.metadata = metadata
        return normalized

    @staticmethod
    def _result_planes(result: ScoredResult) -> Tuple[str, ...]:
        raw = result.metadata.get("fusion_planes")
        if isinstance(raw, (list, tuple)):
            planes = tuple(
                dict.fromkeys(
                    str(plane) for plane in raw if isinstance(plane, str) and plane
                )
            )
            if planes:
                return planes
        return (result.plane,) if result.plane else ()

    def _refresh_result_freshness(
        self,
        results: List[ScoredResult],
    ) -> List[ScoredResult]:
        """Refresh fused freshness metadata even when the ranking came from cache."""
        refreshed: List[ScoredResult] = []
        for result in results:
            planes = self._result_planes(result)
            per_plane: Dict[str, Dict[str, Any]] = {}
            for plane in planes:
                metadata = self._freshness.metadata(plane)
                per_plane[plane] = (
                    {"tracked": False, "stale": None}
                    if metadata is None
                    else {"tracked": True, **metadata}
                )
            copied = replace(result, metadata=dict(result.metadata))
            copied.metadata["fusion_freshness"] = per_plane
            copied.metadata["stale"] = any(
                row.get("stale") is True for row in per_plane.values()
            )
            copied.metadata["freshness_complete"] = all(
                row.get("tracked") is True for row in per_plane.values()
            )
            refreshed.append(copied)
        return refreshed

    def _record_receipt(
        self,
        *,
        query: str,
        generation: int,
        considered_planes: Tuple[str, ...],
        failed_planes: Tuple[str, ...],
        results: List[ScoredResult],
        source: str,
        scope_digest_value: str,
    ) -> RetrievalReceipt:
        fragment_planes = tuple(
            (result.fragment_id, self._result_planes(result))
            for result in results
            if result.fragment_id and self._result_planes(result)
        )
        candidate_planes = tuple(
            sorted(
                {
                    plane
                    for _, planes in fragment_planes
                    for plane in planes
                }
            )
        )
        with self._state_lock:
            self._receipt_sequence += 1
            sequence = self._receipt_sequence
            digest = query_digest(query)
            receipt = RetrievalReceipt(
                receipt_id=receipt_id(sequence, digest, generation),
                query_digest=digest,
                generation=generation,
                scope_digest=scope_digest_value,
                considered_planes=tuple(dict.fromkeys(considered_planes)),
                candidate_planes=candidate_planes,
                failed_planes=tuple(dict.fromkeys(failed_planes)),
                fragment_planes=fragment_planes,
                partial=bool(failed_planes),
                created_ns=time.time_ns(),
                source=source,
            )
            self._receipts.record(receipt)
            self._stats["receipts_created"] += 1
            if receipt.partial:
                self._stats["partial_queries"] += 1
            self._stats["stale_results"] += sum(
                1
                for result in results
                if result.metadata.get("stale") is True
            )
        return receipt

    def _emit_cache_hit(self, query: str, hits: int) -> None:
        if self._bus:
            self._bus.emit("retrieval.cache_hit", {"query": query, "hits": hits})

    def _finish_inflight(self, cache_key: str, flight: Event) -> None:
        """Release waiters for a cache key without disturbing a newer flight."""
        with self._state_lock:
            if self._inflight.get(cache_key) is flight:
                self._inflight.pop(cache_key, None)
            flight.set()

    def _invalidate_cache_locked(self) -> None:
        """Advance result generation after any ranking-affecting state change."""
        self._cache_generation += 1
        self._cache.clear()

    def attach_weight_learner(self, learner: Any) -> Any:
        """Attach/replace adaptive fusion state and invalidate prior rankings."""
        required = ("effective_weights", "observe", "stats")
        if learner is None or any(not callable(getattr(learner, name, None)) for name in required):
            raise TypeError("learner must provide effective_weights(), observe(), and stats()")
        with self._state_lock:
            if learner is self._weight_learner:
                return learner
            self._weight_learner = learner
            self._invalidate_cache_locked()
        return learner

    def export_weight_state(self) -> Optional[Dict[str, Any]]:
        """Return a durable learner checkpoint when adaptive fusion is enabled."""
        with self._state_lock:
            learner = self._weight_learner
            if learner is None:
                return None
            snapshot = getattr(learner, "snapshot", None)
            if not callable(snapshot):
                raise TypeError("attached learner does not support durable snapshots")
            return snapshot()

    def restore_weight_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Restore adaptive fusion state and invalidate rankings from old weights."""
        from skeleton.retrieval.plane_weights import PlaneWeightLearner

        learner = PlaneWeightLearner.from_snapshot(state)
        self.attach_weight_learner(learner)
        return learner.stats()

    def export_retrieval_state(self) -> Dict[str, Any]:
        """Checkpoint adaptive feedback authority, receipts, and freshness together."""
        with self._state_lock:
            learner = self._weight_learner
            learner_state = None
            if learner is not None:
                snapshot = getattr(learner, "snapshot", None)
                if not callable(snapshot):
                    raise TypeError("attached learner does not support durable snapshots")
                learner_state = snapshot()
            return {
                "version": self._RETRIEVAL_STATE_VERSION,
                "receipt_sequence": self._receipt_sequence,
                "learner": learner_state,
                "receipts": self._receipts.snapshot(),
                "freshness": self._freshness.snapshot(),
            }

    def restore_retrieval_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically restore durable adaptive retrieval authority."""
        from skeleton.retrieval.plane_weights import PlaneWeightLearner

        if not isinstance(state, dict) or state.get("version") != self._RETRIEVAL_STATE_VERSION:
            raise ValueError("unsupported retrieval state version")
        sequence = state.get("receipt_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("receipt_sequence must be a non-negative integer")
        learner_payload = state.get("learner")
        learner = (
            None
            if learner_payload is None
            else PlaneWeightLearner.from_snapshot(learner_payload)
        )
        receipts = ReceiptLedger.from_snapshot(state.get("receipts"))
        retained_receipts = len(receipts.recent(receipts.max_entries))
        if sequence < retained_receipts:
            raise ValueError("receipt_sequence cannot trail retained receipt count")
        freshness = FreshnessRegistry.from_snapshot(state.get("freshness"))

        with self._state_lock:
            self._weight_learner = learner
            self._receipts = receipts
            self._freshness = freshness
            self._receipt_sequence = sequence
            self._invalidate_cache_locked()
            return {
                "receipt_sequence": self._receipt_sequence,
                "receipts": len(self._receipts.recent(self._receipts.max_entries)),
                "learner": None if learner is None else learner.stats(),
                "freshness_revision": self._freshness.revision,
            }

    def recent_receipts(self, limit: int = 20) -> Tuple[RetrievalReceipt, ...]:
        return self._receipts.recent(limit)

    def retrieve_scoped(
        self,
        query: str,
        scope: Mapping[str, str] | RetrievalScope,
        k: int = 8,
        use_cache: bool = True,
    ) -> List[ScoredResult]:
        """Retrieve only through planes that enforce authorization before ranking."""
        resolved = (
            scope
            if isinstance(scope, RetrievalScope)
            else RetrievalScope.from_mapping(scope)
        )
        with self._state_lock:
            unsupported = [
                name
                for name, retriever in self._planes.items()
                if not callable(getattr(retriever, "query_scoped", None))
            ]
        if unsupported:
            raise ScopedRetrievalError(
                "scoped retrieval refused because plane(s) lack query_scoped: "
                + ", ".join(sorted(unsupported))
            )
        return self.retrieve(
            query,
            k=k,
            use_cache=use_cache,
            _scope=resolved,
        )

    def retrieve_scoped_with_receipt(
        self,
        query: str,
        scope: Mapping[str, str] | RetrievalScope,
        k: int = 8,
        use_cache: bool = True,
    ) -> Tuple[List[ScoredResult], RetrievalReceipt]:
        resolved = (
            scope
            if isinstance(scope, RetrievalScope)
            else RetrievalScope.from_mapping(scope)
        )
        with self._state_lock:
            unsupported = [
                name
                for name, retriever in self._planes.items()
                if not callable(getattr(retriever, "query_scoped", None))
            ]
        if unsupported:
            raise ScopedRetrievalError(
                "scoped retrieval refused because plane(s) lack query_scoped: "
                + ", ".join(sorted(unsupported))
            )
        sink: List[RetrievalReceipt] = []
        results = self.retrieve(
            query,
            k=k,
            use_cache=use_cache,
            _receipt_sink=sink,
            _scope=resolved,
        )
        if not sink:
            raise RuntimeError("scoped retrieval completed without a receipt")
        return results, sink[-1]

    def retrieve_with_receipt(
        self,
        query: str,
        k: int = 8,
        use_cache: bool = True,
    ) -> Tuple[List[ScoredResult], RetrievalReceipt]:
        sink: List[RetrievalReceipt] = []
        results = self.retrieve(
            query,
            k=k,
            use_cache=use_cache,
            _receipt_sink=sink,
        )
        if not sink:
            raise RuntimeError("retrieval completed without a receipt")
        return results, sink[-1]

    def retrieve(
        self,
        query: str,
        k: int = 8,
        use_cache: bool = True,
        *,
        _receipt_sink: Optional[List[RetrievalReceipt]] = None,
        _scope: Optional[RetrievalScope] = None,
    ) -> List[ScoredResult]:
        """Query registered planes concurrently and fuse deterministic results."""
        t0 = time.perf_counter()
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise ValueError("k must be a non-negative integer")
        with self._state_lock:
            generation = self._cache_generation
            plane_items = tuple(self._planes.items())

        considered_planes = tuple(name for name, _ in plane_items)
        freshness_token = self._freshness.cache_token()
        scope_token = _scope.digest if _scope is not None else "unscoped"
        cache_key = (
            f"{generation}:{freshness_token}:{scope_token}:{k}:{query_digest(query)}"
        )
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                cached_list = self._refresh_result_freshness(list(cached))
                with self._state_lock:
                    self._stats["cache_hits"] += 1
                receipt = self._record_receipt(
                    query=query,
                    generation=generation,
                    considered_planes=considered_planes,
                    failed_planes=(),
                    results=cached_list,
                    source="cache",
                    scope_digest_value="" if _scope is None else _scope.digest,
                )
                if _receipt_sink is not None:
                    _receipt_sink.append(receipt)
                self._emit_cache_hit(query, len(cached_list))
                return cached_list

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
                cached_list = self._refresh_result_freshness(list(cached))
                with self._state_lock:
                    self._stats["cache_hits"] += 1
                receipt = self._record_receipt(
                    query=query,
                    generation=generation,
                    considered_planes=considered_planes,
                    failed_planes=(),
                    results=cached_list,
                    source="cache",
                    scope_digest_value="" if _scope is None else _scope.digest,
                )
                if _receipt_sink is not None:
                    _receipt_sink.append(receipt)
                self._emit_cache_hit(query, len(cached_list))
                return cached_list

            # A topology/ingestion generation change can intentionally prevent
            # the leader from caching its old-generation result. Retry against
            # the current generation rather than serving that stale snapshot.
            return self.retrieve(
                query,
                k=k,
                use_cache=True,
                _receipt_sink=_receipt_sink,
                _scope=_scope,
            )

        try:
            if use_cache:
                # Close the handoff race where a previous flight populated the
                # cache after our first miss but before this caller became leader.
                cached = self._cache.get(cache_key)
                if cached is not None:
                    cached_list = self._refresh_result_freshness(list(cached))
                    with self._state_lock:
                        self._stats["cache_hits"] += 1
                    receipt = self._record_receipt(
                        query=query,
                        generation=generation,
                        considered_planes=considered_planes,
                        failed_planes=(),
                        results=cached_list,
                        source="cache",
                    )
                    if _receipt_sink is not None:
                        _receipt_sink.append(receipt)
                    self._emit_cache_hit(query, len(cached_list))
                    return cached_list

            results_by_plane: Dict[str, List[ScoredResult]] = {}
            failures: List[str] = []

            if len(plane_items) == 1:
                plane_name, retriever = plane_items[0]
                try:
                    normalized = self._query_plane(
                        plane_name,
                        retriever,
                        query,
                        k,
                        _scope,
                    )
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
                                _scope,
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

            if _scope is not None and failures:
                raise ScopedRetrievalError(
                    "scoped retrieval aborted because plane(s) failed: "
                    + ", ".join(sorted(failures))
                )

            fused = self._refresh_result_freshness(
                self._fuse(results_by_plane, k)
            )
            receipt = self._record_receipt(
                query=query,
                generation=generation,
                considered_planes=considered_planes,
                failed_planes=tuple(failures),
                results=fused,
                source="live",
                scope_digest_value="" if _scope is None else _scope.digest,
            )
            if _receipt_sink is not None:
                _receipt_sink.append(receipt)

            # Generation checking closes a subtle invalidation race: a query that
            # started before register_plane()/ingest_document() may finish after the
            # cache was cleared. It must not repopulate that cache with stale results.
            if use_cache:
                with self._state_lock:
                    if generation == self._cache_generation and not failures:
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
                        "receipt_id": receipt.receipt_id,
                        "scope_digest": receipt.scope_digest,
                        "partial": receipt.partial,
                    },
                )
                self._bus.emit(
                    "retrieval.quad.query",
                    {
                        "query": query,
                        "planes": list(results_by_plane.keys()),
                        "failed_planes": list(failures),
                        "results": len(fused),
                        "receipt_id": receipt.receipt_id,
                        "scope_digest": receipt.scope_digest,
                        "partial": receipt.partial,
                    },
                )

            return fused
        finally:
            if use_cache and owns_flight and flight is not None:
                self._finish_inflight(cache_key, flight)


    @property
    def weights(self) -> Dict[str, float]:
        """Static plane weights, or the attached learner's effective weights."""
        with self._state_lock:
            learner = self._weight_learner
            if learner is None:
                return dict(self._static_weights)
            return learner.effective_weights()

    def observe_receipt(
        self,
        receipt_id_value: str,
        used_fragment_ids,
    ) -> Dict[str, Any]:
        """Apply feedback exactly once against fragments actually returned."""
        from skeleton.retrieval.plane_weights import PlaneWeightLearner

        if isinstance(used_fragment_ids, (str, bytes)) or not isinstance(
            used_fragment_ids, (list, tuple, set)
        ):
            raise TypeError("used_fragment_ids must be a list, tuple, or set")
        if any(not isinstance(item, str) or not item for item in used_fragment_ids):
            raise ValueError("used_fragment_ids must contain non-empty strings")
        used_fragments = tuple(dict.fromkeys(used_fragment_ids))
        with self._state_lock:
            receipt = self._receipts.require_available(receipt_id_value)
            unknown = sorted(set(used_fragments) - set(receipt.fragment_ids))
            if unknown:
                raise ValueError(
                    "feedback references fragment(s) absent from receipt: "
                    + ", ".join(unknown)
                )
            if not receipt.candidate_planes:
                raise ValueError("retrieval receipt has no candidate planes to train")
            used_planes = tuple(
                sorted(
                    {
                        plane
                        for fragment_id in used_fragments
                        for plane in receipt.planes_for_fragment(fragment_id)
                    }
                )
            )
            if self._weight_learner is None:
                self._weight_learner = PlaneWeightLearner(self._static_weights)
            self._weight_learner.observe(
                used_planes,
                all_planes=receipt.candidate_planes,
            )
            self._receipts.mark_consumed(receipt_id_value)
            self._stats["feedback_consumed"] += 1
            self._invalidate_cache_locked()
            stats = self._weight_learner.stats()

        if self._bus:
            self._bus.emit(
                "retrieval.feedback.attributed",
                {
                    "receipt_id": receipt.receipt_id,
                    "query_digest": receipt.query_digest,
                    "used_fragments": len(used_fragments),
                    "used_planes": list(used_planes),
                    "candidate_planes": list(receipt.candidate_planes),
                    "updates": stats["updates"],
                },
            )
        return stats

    def observe(self, used_planes, *, all_planes=None) -> Dict[str, Any]:
        """Record unattributed compatibility feedback and invalidate old rankings."""
        from skeleton.retrieval.plane_weights import PlaneWeightLearner

        used = tuple(used_planes)
        considered = tuple(all_planes) if all_planes is not None else None
        with self._state_lock:
            if self._weight_learner is None:
                self._weight_learner = PlaneWeightLearner(self._static_weights)
            self._weight_learner.observe(used, all_planes=considered)
            self._invalidate_cache_locked()
            stats = self._weight_learner.stats()

        if self._bus:
            self._bus.emit(
                "retrieval.feedback.updated",
                {
                    "used_planes": sorted(set(used)),
                    "all_planes": sorted(set(considered)) if considered is not None else None,
                    "updates": stats["updates"],
                    "weights": stats["weights"],
                },
            )
        return stats

    def _fuse(self, results_by_plane: Dict[str, List[ScoredResult]], top_k: int) -> List[ScoredResult]:
        """RRF by default. An attached learner scales each plane's contribution."""
        learner = self._weight_learner
        if learner is None:
            return self._fuser.fuse(results_by_plane, top_k=top_k)
        return self._fuser.weighted_rrf(
            results_by_plane,
            learner.effective_weights(),
            top_k=top_k,
        )

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
            payload = {
                **self._stats,
                "planes_used": list(self._plane_history),
                "planes_registered": len(self._planes),
                "cache_size": self._cache.size(),
                "cache_generation": self._cache_generation,
                "receipt_sequence": self._receipt_sequence,
                "retained_receipts": len(
                    self._receipts.recent(self._receipts.max_entries)
                ),
                "freshness_revision": self._freshness.revision,
            }
            if self._weight_learner is not None:
                payload["learner"] = self._weight_learner.stats()
            return payload
