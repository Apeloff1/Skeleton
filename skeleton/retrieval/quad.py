"""
Skeleton Retrieval — Quad-plane retriever (RAG+CAG+MAG+KAG)

Provides:
- QuadRetriever: Unified retrieval across four memory planes
- PlaneResult: Results from a single plane

Ingestion feeds RAG with chunks AND the KAG plane with triples
extracted from the text, so the knowledge graph self-populates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import EventBus
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
    """

    def __init__(self, bus: Optional[EventBus] = None, extractor: Optional[TripleExtractor] = None):
        self._bus = bus
        self._planes: Dict[str, Any] = {}
        self._fuser = Fuser(strategy=FusionStrategy.RRF)
        self._cache: Dict[str, List[ScoredResult]] = {}
        self._extractor = extractor or TripleExtractor()
        self._stats = {"queries": 0, "cache_hits": 0, "ingested": 0, "triples_extracted": 0, "planes_used": []}

    def register_plane(self, name: str, retriever: Any) -> None:
        """Register a retrieval plane."""
        if retriever is not None:
            self._planes[name] = retriever

    def retrieve(self, query: str, k: int = 8, use_cache: bool = True) -> List[ScoredResult]:
        """Query all registered planes and fuse results."""
        cache_key = f"{query}:{k}"

        if use_cache and cache_key in self._cache:
            self._stats["cache_hits"] += 1
            return self._cache[cache_key]

        self._stats["queries"] += 1

        results_by_plane: Dict[str, List[ScoredResult]] = {}

        for plane_name, retriever in self._planes.items():
            try:
                if hasattr(retriever, "query"):
                    plane_results = retriever.query(query, top_k=k)
                elif hasattr(retriever, "retrieve"):
                    plane_results = retriever.retrieve(query, k=k)
                else:
                    continue

                # Normalize plane tags for fusion provenance
                for r in plane_results:
                    if getattr(r, "plane", None) in (None, "", "rag") and plane_name != "rag":
                        r.plane = plane_name

                if plane_results:
                    results_by_plane[plane_name] = plane_results
                    self._stats["planes_used"].append(plane_name)
            except Exception:
                continue

        fused = self._fuser.fuse(results_by_plane, top_k=k)

        if use_cache:
            self._cache[cache_key] = fused

        if self._bus:
            self._bus.emit("retrieval.quad.query", {
                "query": query,
                "planes": list(results_by_plane.keys()),
                "results": len(fused),
            })

        return fused

    def ingest_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None, salience: float = 0.5) -> int:
        """Ingest a document: chunk into RAG and extract triples into KAG.

        Returns the number of chunks ingested into RAG.
        """
        chunks = 0

        rag = self._planes.get("rag")
        if rag and hasattr(rag, "add"):
            from skeleton.memory.core import Chunk
            chunk = Chunk(text=text, chunk_id=doc_id, metadata=metadata or {})
            rag.add(chunk)
            chunks += 1

        # Self-populate the KAG plane from the same text
        kag = self._planes.get("kag")
        if kag is not None and hasattr(kag, "graph"):
            triples = self._extractor.extract(text)
            for subject, predicate, obj in triples:
                kag.graph.add(subject, predicate, obj)
            self._stats["triples_extracted"] += len(triples)

        # MAG episodic trace for high-salience documents
        mag = self._planes.get("mag")
        if mag is not None and hasattr(mag, "record") and salience >= 0.7:
            mag.record(doc_id, text[:500], tags=(metadata or {}).get("tags", []))

        # Invalidate cache: new content can change rankings
        self._cache.clear()
        self._stats["ingested"] += chunks

        if self._bus:
            self._bus.emit("retrieval.quad.ingested", {
                "doc_id": doc_id,
                "chunks": chunks,
                "triples": self._stats["triples_extracted"],
                "salience": salience,
            })

        return chunks

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "planes_registered": len(self._planes),
            "cache_size": len(self._cache),
        }
