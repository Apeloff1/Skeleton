"""
Skeleton Memory Subsystem — RAG, CAG, MAG, and Trinity fusion

Provides:
- InMemoryTFIDFStore: Sparse retrieval with TF-IDF scoring
- CAGStore: Contextual associative memory
- MAGStore: Multi-agent episodic memory
- MemoryTrinity: Unified query across RAG+CAG+MAG with fusion
- RepetitionScheduler: Spaced repetition for memory consolidation
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.events import EventBus


@dataclass
class Chunk:
    """A text chunk with metadata."""
    text: str
    chunk_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class ScoredChunk:
    """Retrieval result with score and provenance."""
    chunk: Chunk
    score: float
    plane: str = "rag"
    provenance: str = ""


class InMemoryTFIDFStore:
    """In-memory TF-IDF retrieval store (RAG plane)."""

    def __init__(self):
        self._docs: Dict[str, Chunk] = {}
        self._term_freq: Dict[str, Dict[str, int]] = {}  # term -> {doc_id: count}
        self._doc_freq: Dict[str, int] = {}  # term -> doc count
        self._total_docs = 0

    def add(self, chunk: Chunk) -> None:
        self._docs[chunk.chunk_id] = chunk
        terms = self._tokenize(chunk.text)
        freq: Dict[str, int] = {}
        for term in terms:
            freq[term] = freq.get(term, 0) + 1
        
        for term, count in freq.items():
            self._term_freq.setdefault(term, {})[chunk.chunk_id] = count
            self._doc_freq[term] = self._doc_freq.get(term, 0) + 1
        
        self._total_docs += 1

    def query(self, text: str, top_k: int = 5) -> List[ScoredChunk]:
        terms = self._tokenize(text)
        if not terms or self._total_docs == 0:
            return []
        
        scores: Dict[str, float] = {}
        for term in terms:
            if term not in self._term_freq:
                continue
            idf = math.log(self._total_docs / (1 + self._doc_freq.get(term, 0)))
            for doc_id, tf in self._term_freq[term].items():
                tf_weight = 1 + math.log(tf)
                scores[doc_id] = scores.get(doc_id, 0) + tf_weight * idf
        
        # Normalize by doc length
        for doc_id in scores:
            doc_len = len(self._tokenize(self._docs[doc_id].text))
            scores[doc_id] /= math.sqrt(doc_len) if doc_len > 0 else 1
        
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            ScoredChunk(chunk=self._docs[doc_id], score=score, plane="rag")
            for doc_id, score in ranked
        ]

    def stats(self) -> Dict[str, Any]:
        return {
            "documents": len(self._docs),
            "terms": len(self._term_freq),
            "total_docs": self._total_docs,
        }

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [t.lower() for t in text.split() if len(t) > 2]


class CAGStore:
    """Contextual Associative Memory store."""

    def __init__(self):
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._associations: Dict[str, Set[str]] = {}

    def store(self, key: str, value: Any, context: Optional[str] = None) -> None:
        self._entries[key] = {"value": value, "context": context, "stored_at": time.time()}
        if context:
            self._associations.setdefault(key, set()).add(context)

    def recall(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        return entry["value"] if entry else None

    def query(self, context: str) -> List[Dict[str, Any]]:
        results = []
        for key, contexts in self._associations.items():
            if context in contexts:
                entry = self._entries[key]
                results.append({"key": key, "value": entry["value"], "context": context})
        return results

    def stats(self) -> Dict[str, Any]:
        return {"entries": len(self._entries), "associations": len(self._associations)}


class MAGStore:
    """Multi-Agent Episodic Memory store."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._episodes: Dict[str, Dict[str, Any]] = {}
        self._tag_index: Dict[str, Set[str]] = {}

    def record(self, episode_id: str, content: str, tags: Optional[List[str]] = None) -> None:
        self._episodes[episode_id] = {
            "content": content,
            "tags": tags or [],
            "recorded_at": time.time(),
        }
        for tag in (tags or []):
            self._tag_index.setdefault(tag, set()).add(episode_id)

    def recall_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        episode_ids = self._tag_index.get(tag, set())
        return [self._episodes[eid] for eid in episode_ids if eid in self._episodes]

    def stats(self) -> Dict[str, Any]:
        return {
            "episodes": len(self._episodes),
            "tags": len(self._tag_index),
            "agent_id": self.agent_id,
        }


@dataclass
class TrinityResult:
    """Unified result from MemoryTrinity query."""
    facts: List[ScoredChunk]
    persona_frame: List[ScoredChunk]
    personal_history: List[ScoredChunk]
    combined_score: float
    token_estimate: int
    provenance_chain: List[str]


class MemoryTrinity:
    """Unified RAG + CAG + MAG query with fusion."""

    def __init__(self, rag: InMemoryTFIDFStore, cag: CAGStore, mag: MAGStore, bus: Optional[EventBus] = None):
        self.rag = rag
        self.cag = cag
        self.mag = mag
        self._bus = bus

    def query_unified(self, query_text: str, top_k_per_tier: int = 3, metadata_filter: Optional[Dict[str, Any]] = None) -> TrinityResult:
        # Query each plane
        rag_results = self.rag.query(query_text, top_k=top_k_per_tier)
        
        # CAG associative recall
        cag_results = []
        for entry in self.cag.query(query_text):
            chunk = Chunk(text=str(entry["value"]), metadata={"source": "cag", "key": entry["key"]})
            cag_results.append(ScoredChunk(chunk=chunk, score=0.7, plane="cag"))
        
        # MAG episodic recall
        mag_results = []
        for tag in query_text.split():
            for episode in self.mag.recall_by_tag(tag):
                chunk = Chunk(text=episode["content"], metadata={"source": "mag", "tags": episode["tags"]})
                mag_results.append(ScoredChunk(chunk=chunk, score=0.6, plane="mag"))
        
        all_results = rag_results + cag_results + mag_results[:top_k_per_tier]
        
        # RRF fusion
        fused = self._reciprocal_rank_fusion(all_results)
        
        result = TrinityResult(
            facts=fused[:top_k_per_tier],
            persona_frame=cag_results[:top_k_per_tier],
            personal_history=mag_results[:top_k_per_tier],
            combined_score=sum(r.score for r in fused[:top_k_per_tier]) / max(len(fused[:top_k_per_tier]), 1),
            token_estimate=sum(len(r.chunk.text.split()) for r in fused[:top_k_per_tier]) * 1.3,
            provenance_chain=[r.plane for r in fused[:top_k_per_tier]],
        )
        
        if self._bus:
            self._bus.emit("memory.trinity.query", {
                "query": query_text,
                "results": len(all_results),
                "fused": len(fused),
            })
        
        return result

    @staticmethod
    def _reciprocal_rank_fusion(results: List[ScoredChunk], k: int = 60) -> List[ScoredChunk]:
        """RRF: fuse results from multiple retrieval planes."""
        scores: Dict[str, float] = {}
        chunks: Dict[str, Chunk] = {}
        
        for rank, result in enumerate(results, 1):
            cid = result.chunk.chunk_id or hash(result.chunk.text)
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank)
            chunks[cid] = result.chunk
        
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [ScoredChunk(chunk=chunks[cid], score=score, plane="fused") for cid, score in ranked]

    def stats(self) -> Dict[str, Any]:
        return {
            "rag": self.rag.stats(),
            "cag": self.cag.stats(),
            "mag": self.mag.stats(),
        }


class RepetitionScheduler:
    """Spaced repetition scheduler for memory consolidation."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._schedule: Dict[str, Dict[str, Any]] = {}
        self._bus = bus

    def schedule(self, item_id: str, interval_hours: float = 24) -> None:
        now = time.time()
        self._schedule[item_id] = {
            "next_review": now + interval_hours * 3600,
            "interval": interval_hours,
            "repetitions": 0,
        }

    def review(self, item_id: str, performance: float = 1.0) -> float:
        """Process a review, return new interval in hours."""
        if item_id not in self._schedule:
            self.schedule(item_id)
        
        entry = self._schedule[item_id]
        entry["repetitions"] += 1
        
        # SM-2 inspired interval calculation
        if performance >= 0.6:
            entry["interval"] *= (1.5 + 0.1 * performance)
        else:
            entry["interval"] = max(1, entry["interval"] * 0.5)
        
        entry["next_review"] = time.time() + entry["interval"] * 3600
        
        if self._bus:
            self._bus.emit("memory.repetition.review", {
                "item": item_id,
                "performance": performance,
                "interval": entry["interval"],
            })
        
        return entry["interval"]

    def due_items(self) -> List[str]:
        now = time.time()
        return [item_id for item_id, entry in self._schedule.items() if entry["next_review"] <= now]

    def stats(self) -> Dict[str, Any]:
        return {
            "scheduled": len(self._schedule),
            "due_now": len(self.due_items()),
        }
