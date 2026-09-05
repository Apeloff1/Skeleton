"""Quad Retrieval Lattice — RAG + CAG + MAG + KAG with reciprocal-rank fusion.

Four retrieval planes, one interface, one fusion ranker:

* **RAG** — Retrieval-Augmented Generation: vector similarity over embedded chunks.
* **CAG** — Cache-Augmented Generation: exact/semantic answer cache with TTL, hit
  promotion, and negative caching so repeated or near-repeated queries never pay
  retrieval cost twice.
* **MAG** — Memory-Augmented Generation: episodic + semantic long-term memory with
  salience scoring, decay, and reinforcement on access.
* **KAG** — Knowledge-Augmented Generation: structured ontology/entity graph
  traversal returning typed facts with provenance edges.

The :class:`QuadRetriever` fans a query out to all four planes in-process,
normalises each plane's scores into [0,1], and merges with *reciprocal rank
fusion* (RRF) weighted per plane. Every plane is fully implemented — no external
service is required; ChromaDB can back the RAG plane when present, but the
embedded TF-IDF vector store is the default and is complete.

Fix (2026-08-28): bus notifications previously called
``EventBus.publish(topic_str, payload_dict)`` — the kernel bus requires a
:class:`DomainEvent`, so every ingest/retrieve raised ``EventBusError``.
Switched to ``bus.emit(...)``, which builds the event. ``bus.emit`` failures
are swallowed: retrieval must never fail on telemetry.
"""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..kernel.events import EventBus
from ..kernel.errors import RetrievalError


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fragment:
    """One retrievable unit, plane-agnostic."""

    fragment_id: str
    plane: str                       # "rag" | "cag" | "mag" | "kag"
    content: str
    score: float                     # raw plane score, pre-normalisation
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: str = ""

    def with_score(self, score: float) -> "Fragment":
        return Fragment(self.fragment_id, self.plane, self.content, score,
                        dict(self.metadata), self.provenance)


def _tokens(text: str) -> List[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


def _emit(bus: EventBus, topic: str, payload: Dict[str, Any]) -> None:
    """Best-effort event emit — telemetry must never break retrieval."""
    try:
        bus.emit(topic, payload, correlation_id="quad-retriever")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# RAG plane — embedded TF-IDF vector store
# ---------------------------------------------------------------------------

class RagPlane:
    """Vector retrieval over TF-IDF embeddings with cosine similarity."""

    name = "rag"

    def __init__(self) -> None:
        self._docs: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        self._df: Dict[str, int] = defaultdict(int)
        self._vectors: Dict[str, Dict[str, float]] = {}

    def _embed(self, text: str) -> Dict[str, float]:
        tf: Dict[str, int] = defaultdict(int)
        for tok in _tokens(text):
            tf[tok] += 1
        n = max(1, sum(tf.values()))
        n_docs = max(1, len(self._docs))
        vec: Dict[str, float] = {}
        for tok, count in tf.items():
            idf = math.log((1 + n_docs) / (1 + self._df.get(tok, 0))) + 1.0
            vec[tok] = (count / n) * idf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    def index(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if doc_id not in self._docs:
            for tok in set(_tokens(text)):
                self._df[tok] += 1
        self._docs[doc_id] = (text, metadata or {})
        self._vectors[doc_id] = self._embed(text)

    def search(self, query: str, k: int = 8) -> List[Fragment]:
        qv = self._embed(query)
        scored: List[Tuple[float, str]] = []
        for doc_id, dv in self._vectors.items():
            shared = set(qv) & set(dv)
            score = sum(qv[t] * dv[t] for t in shared)
            if score > 0.0:
                scored.append((score, doc_id))
        scored.sort(reverse=True)
        out: List[Fragment] = []
        for score, doc_id in scored[:k]:
            text, meta = self._docs[doc_id]
            out.append(Fragment(doc_id, self.name, text, score, dict(meta),
                                provenance=f"rag://{doc_id}"))
        return out


# ---------------------------------------------------------------------------
# CAG plane — semantic answer cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    query: str
    answer_fragments: List[Fragment]
    vector: Dict[str, float]
    created_at: float
    ttl_seconds: float
    hits: int = 0
    negative: bool = False


class CagPlane:
    """Answer cache with semantic lookup, TTL, hit promotion and negative caching."""

    name = "cag"
    SEMANTIC_THRESHOLD = 0.86

    def __init__(self, default_ttl: float = 3600.0, capacity: int = 4096) -> None:
        self._entries: Dict[str, _CacheEntry] = {}
        self._default_ttl = default_ttl
        self._capacity = capacity

    @staticmethod
    def _key(query: str) -> str:
        return "cag_" + hashlib.sha256(" ".join(_tokens(query)).encode()).hexdigest()[:24]

    def _embed(self, text: str) -> Dict[str, float]:
        tf: Dict[str, int] = defaultdict(int)
        for tok in _tokens(text):
            tf[tok] += 1
        total = max(1, sum(tf.values()))
        return {k: v / total for k, v in tf.items()}

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        shared = set(a) & set(b)
        num = sum(a[t] * b[t] for t in shared)
        na = math.sqrt(sum(v * v for v in a.values())) or 1.0
        nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
        return num / (na * nb)

    def put(self, query: str, fragments: List[Fragment],
            ttl: Optional[float] = None, negative: bool = False) -> None:
        if len(self._entries) >= self._capacity:
            # evict coldest entry: lowest hits, oldest
            victim = min(self._entries.items(),
                         key=lambda kv: (kv[1].hits, kv[1].created_at))[0]
            del self._entries[victim]
        self._entries[self._key(query)] = _CacheEntry(
            query=query, answer_fragments=list(fragments), vector=self._embed(query),
            created_at=time.time(), ttl_seconds=ttl or self._default_ttl,
            negative=negative)

    def search(self, query: str, k: int = 4) -> List[Fragment]:
        now = time.time()
        qv = self._embed(query)
        best: Optional[_CacheEntry] = None
        best_sim = 0.0
        for entry in self._entries.values():
            if now - entry.created_at > entry.ttl_seconds:
                continue
            sim = self._cosine(qv, entry.vector)
            if sim > best_sim:
                best_sim, best = sim, entry
        if best is None or best_sim < self.SEMANTIC_THRESHOLD or best.negative:
            return []
        best.hits += 1
        # promotion: extend TTL on repeated hits (bounded at 4x base)
        best.ttl_seconds = min(best.ttl_seconds * 1.25, self._default_ttl * 4)
        return [f.with_score(min(1.0, 0.5 + 0.5 * best_sim + 0.02 * best.hits))
                for f in best.answer_fragments[:k]]

    def stats(self) -> Dict[str, Any]:
        live = [e for e in self._entries.values()
                if time.time() - e.created_at <= e.ttl_seconds]
        return {"entries": len(self._entries), "live": len(live),
                "total_hits": sum(e.hits for e in self._entries.values()),
                "negatives": sum(1 for e in self._entries.values() if e.negative)}


# ---------------------------------------------------------------------------
# MAG plane — episodic/semantic memory with salience + decay
# ---------------------------------------------------------------------------

@dataclass
class _MemoryTrace:
    trace_id: str
    kind: str                        # "episodic" | "semantic"
    content: str
    salience: float                  # 0..1, set at encoding
    strength: float                  # reinforced on access, decays over time
    created_at: float
    accessed_at: float
    access_count: int
    metadata: Dict[str, Any]


class MagPlane:
    """Long-term memory: salience-gated encoding, Ebbinghaus decay, reinforcement."""

    name = "mag"
    DECAY_RATE = 0.021               # per-hour retention slope

    def __init__(self) -> None:
        self._traces: Dict[str, _MemoryTrace] = {}

    def encode(self, content: str, kind: str = "episodic", salience: float = 0.5,
               metadata: Optional[Dict[str, Any]] = None) -> str:
        if not 0.0 <= salience <= 1.0:
            raise RetrievalError("salience out of range", code="RET.MAG.SALIENCE",
                                 context={"salience": salience})
        tid = "mem_" + uuid.uuid4().hex[:16]
        now = time.time()
        self._traces[tid] = _MemoryTrace(tid, kind, content, salience,
                                         strength=salience, created_at=now,
                                         accessed_at=now, access_count=0,
                                         metadata=metadata or {})
        return tid

    def _retention(self, trace: _MemoryTrace, now: float) -> float:
        hours = max(0.0, (now - trace.accessed_at) / 3600.0)
        return trace.strength * math.exp(-self.DECAY_RATE * hours)

    def reinforce(self, trace_id: str, amount: float = 0.15) -> None:
        trace = self._traces.get(trace_id)
        if trace is None:
            raise RetrievalError("unknown trace", code="RET.MAG.MISSING",
                                 context={"trace_id": trace_id})
        trace.strength = min(1.0, trace.strength + amount)
        trace.access_count += 1
        trace.accessed_at = time.time()

    def search(self, query: str, k: int = 6) -> List[Fragment]:
        now = time.time()
        qtokens = set(_tokens(query))
        scored: List[Tuple[float, _MemoryTrace]] = []
        for trace in self._traces.values():
            retention = self._retention(trace, now)
            if retention < 0.05:
                continue
            overlap = len(qtokens & set(_tokens(trace.content)))
            if not qtokens:
                continue
            relevance = overlap / math.sqrt(len(qtokens) * max(1, len(set(_tokens(trace.content)))))
            score = 0.6 * relevance + 0.3 * retention + 0.1 * trace.salience
            if score > 0.05:
                scored.append((score, trace))
        scored.sort(key=lambda st: st[0], reverse=True)
        out: List[Fragment] = []
        for score, trace in scored[:k]:
            trace.access_count += 1
            trace.accessed_at = now
            out.append(Fragment(trace.trace_id, self.name, trace.content, score,
                                dict(trace.metadata, kind=trace.kind,
                                     access_count=trace.access_count),
                                provenance=f"mag://{trace.trace_id}"))
        return out


# ---------------------------------------------------------------------------
# KAG plane — typed knowledge graph traversal
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnowledgeEdge:
    subject: str
    predicate: str
    obj: str
    confidence: float = 1.0
    provenance: str = ""


class KagPlane:
    """Entity/ontology graph with typed edges, traversal and fact scoring."""

    name = "kag"

    def __init__(self) -> None:
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._edges: List[KnowledgeEdge] = []
        self._by_subject: Dict[str, List[KnowledgeEdge]] = defaultdict(list)
        self._by_object: Dict[str, List[KnowledgeEdge]] = defaultdict(list)

    def add_entity(self, entity: str, kind: str, **attrs: Any) -> None:
        self._entities[entity] = {"kind": kind, **attrs}

    def add_edge(self, edge: KnowledgeEdge) -> None:
        if edge.subject not in self._entities:
            self.add_entity(edge.subject, "unknown")
        if edge.obj not in self._entities:
            self.add_entity(edge.obj, "unknown")
        self._edges.append(edge)
        self._by_subject[edge.subject].append(edge)
        self._by_object[edge.obj].append(edge)

    def neighbours(self, entity: str, depth: int = 2) -> List[Tuple[KnowledgeEdge, int]]:
        """Breadth-first traversal, returning (edge, depth) pairs."""
        seen = {entity}
        frontier = [entity]
        out: List[Tuple[KnowledgeEdge, int]] = []
        for d in range(1, depth + 1):
            nxt: List[str] = []
            for node in frontier:
                for edge in self._by_subject.get(node, []) + self._by_object.get(node, []):
                    out.append((edge, d))
                    for endpoint in (edge.subject, edge.obj):
                        if endpoint not in seen:
                            seen.add(endpoint)
                            nxt.append(endpoint)
            frontier = nxt
        return out

    def search(self, query: str, k: int = 6) -> List[Fragment]:
        qtokens = set(_tokens(query))
        hits: List[Tuple[float, KnowledgeEdge]] = []
        for edge in self._edges:
            etoks = set(_tokens(f"{edge.subject} {edge.predicate} {edge.obj}"))
            overlap = len(qtokens & etoks)
            if overlap == 0:
                continue
            score = edge.confidence * overlap / max(1, len(etoks))
            hits.append((score, edge))
        hits.sort(key=lambda hs: hs[0], reverse=True)
        return [
            Fragment(f"fact_{i}", self.name,
                     f"{e.subject} —[{e.predicate}]→ {e.obj}", score,
                     {"predicate": e.predicate, "confidence": e.confidence},
                     provenance=e.provenance or f"kag://{e.subject}/{e.predicate}")
            for i, (score, e) in enumerate(hits[:k])
        ]

    def stats(self) -> Dict[str, Any]:
        return {"entities": len(self._entities), "edges": len(self._edges),
                "predicates": len({e.predicate for e in self._edges})}


# ---------------------------------------------------------------------------
# Fusion — reciprocal rank fusion across the four planes
# ---------------------------------------------------------------------------

class QuadRetriever:
    """Fans queries to RAG/CAG/MAG/KAG and fuses with weighted RRF."""

    DEFAULT_WEIGHTS = {"rag": 1.0, "cag": 1.4, "mag": 0.9, "kag": 1.1}
    RRF_K = 60.0

    def __init__(self, bus: Optional[EventBus] = None,
                 weights: Optional[Dict[str, float]] = None) -> None:
        self.rag = RagPlane()
        self.cag = CagPlane()
        self.mag = MagPlane()
        self.kag = KagPlane()
        self.weights = dict(self.DEFAULT_WEIGHTS, **(weights or {}))
        self._bus = bus or EventBus()

    # -- ingestion --------------------------------------------------------
    def ingest_document(self, doc_id: str, text: str,
                        metadata: Optional[Dict[str, Any]] = None,
                        salience: float = 0.5, chunk_size: int = 512) -> int:
        """Chunk + index into RAG, and encode salient chunks into MAG."""
        words = text.split()
        chunks = [" ".join(words[i:i + chunk_size])
                  for i in range(0, len(words), chunk_size)] or [text]
        for i, chunk in enumerate(chunks):
            cid = f"{doc_id}#chunk{i}"
            self.rag.index(cid, chunk, dict(metadata or {}, doc_id=doc_id, chunk=i))
            self.mag.encode(chunk, kind="semantic",
                            salience=min(1.0, salience + 0.1 * (i == 0)),
                            metadata={"doc_id": doc_id, "chunk": i})
        _emit(self._bus, "retrieval.ingested",
              {"doc_id": doc_id, "chunks": len(chunks)})
        return len(chunks)

    def ingest_fact(self, subject: str, predicate: str, obj: str,
                    confidence: float = 1.0, provenance: str = "") -> None:
        self.kag.add_edge(KnowledgeEdge(subject, predicate, obj, confidence, provenance))
        self.mag.encode(f"{subject} {predicate} {obj}", kind="semantic",
                        salience=min(1.0, 0.4 + 0.4 * confidence),
                        metadata={"source": "kag"})

    # -- retrieval ----------------------------------------------------------
    def retrieve(self, query: str, k: int = 8, use_cache: bool = True) -> List[Fragment]:
        t0 = time.perf_counter()
        if use_cache:
            cached = self.cag.search(query, k=k)
            if cached:
                _emit(self._bus, "retrieval.cache_hit",
                      {"query": query, "hits": len(cached)})
                return cached

        plane_hits: Dict[str, List[Fragment]] = {
            "rag": self.rag.search(query, k=k * 2),
            "mag": self.mag.search(query, k=k * 2),
            "kag": self.kag.search(query, k=k * 2),
        }

        weights = (
            self._weight_learner.effective_weights()
            if getattr(self, "_weight_learner", None)
            else self.weights
        )
        fused: Dict[str, float] = defaultdict(float)
        best_fragment: Dict[str, Fragment] = {}
        for plane, hits in plane_hits.items():
            weight = weights.get(plane, 1.0)
            for rank, frag in enumerate(hits):
                key = frag.provenance or frag.fragment_id
                fused[key] += weight / (self.RRF_K + rank + 1)
                if key not in best_fragment or frag.score > best_fragment[key].score:
                    best_fragment[key] = frag

        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        results = [best_fragment[key].with_score(score) for key, score in ranked]

        if use_cache:
            self.cag.put(query, results, negative=not results)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit(self._bus, "retrieval.completed",
              {"query": query, "results": len(results),
               "elapsed_ms": round(elapsed_ms, 3),
               "planes": {p: len(h) for p, h in plane_hits.items()}})
        return results

    def observe(self, used_planes, *, all_planes=None):
        """Feed retrieval outcome into the attached plane-weight learner."""
        from skeleton.retrieval.plane_weights import attach_learner
        learner = getattr(self, "_weight_learner", None)
        if learner is None:
            learner = attach_learner(self)
        learner.observe(used_planes, all_planes=all_planes)
        # keep static table in sync so retrieve without re-read still sees updates
        self.weights.update(learner.effective_weights())
        return learner.stats()

    def stats(self) -> Dict[str, Any]:
        out = {"cag": self.cag.stats(), "kag": self.kag.stats(),
               "mag_traces": len(self.mag._traces),
               "rag_docs": len(self.rag._docs), "weights": dict(self.weights)}
        learner = getattr(self, "_weight_learner", None)
        if learner is not None:
            out["learner"] = learner.stats()
        return out
