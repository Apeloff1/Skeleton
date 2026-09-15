from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import math
import hashlib


class DiaryVectorIndex:
    """HNSW when available; cosine brute-force fallback. Deterministic offline embed."""

    def __init__(self, dim: int = 128, space: str = "cosine"):
        self.dim = dim
        self.space = space
        self._ids: List[str] = []
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._vectors: List[List[float]] = []
        self._hnsw = None
        self._id_to_label: Dict[str, int] = {}
        self._label_to_id: Dict[int, str] = {}
        self._embed_fn = None
        self._init_hnsw()

    def _init_hnsw(self):
        try:
            import hnswlib

            idx = hnswlib.Index(space="cosine", dim=self.dim)
            idx.init_index(max_elements=10000, ef_construction=200, M=16)
            idx.set_ef(64)
            self._hnsw = idx
        except Exception:
            self._hnsw = None

    def set_embed_fn(self, fn):
        self._embed_fn = fn

    def embed(self, text: str) -> List[float]:
        if self._embed_fn:
            v = self._embed_fn(text)
            if len(v) != self.dim:
                raise ValueError(f"embed_fn dim {len(v)} != {self.dim}")
            return [float(x) for x in v]
        vec = [0.0] * self.dim
        tokens = text.lower().split()
        if not tokens:
            return vec
        for tok in tokens:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(self.dim):
                vec[i] += (h[i % len(h)] - 128) / 128.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def add(self, entry_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        v = self.embed(text)
        metadata = metadata or {}
        if entry_id in self._id_to_label:
            self._meta[entry_id] = metadata
            try:
                label = self._id_to_label[entry_id]
                self._vectors[label] = v
            except Exception:
                pass
            return

        label = len(self._ids)
        self._ids.append(entry_id)
        self._vectors.append(v)
        self._meta[entry_id] = metadata
        self._id_to_label[entry_id] = label
        self._label_to_id[label] = entry_id
        if self._hnsw is not None:
            try:
                if label >= self._hnsw.get_max_elements():
                    self._hnsw.resize_index(label + 10000)
                self._hnsw.add_items([v], [label])
            except Exception:
                self._hnsw = None

    async def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        if not self._ids:
            return []
        q = self.embed(query)
        k = min(k, len(self._ids))
        if self._hnsw is not None:
            try:
                labels, distances = self._hnsw.knn_query([q], k=k)
                out = []
                for lab, dist in zip(labels[0], distances[0]):
                    eid = self._label_to_id.get(int(lab))
                    if not eid:
                        continue
                    out.append(
                        {
                            "id": eid,
                            "score": float(1.0 - dist) if self.space == "cosine" else float(-dist),
                            "metadata": self._meta.get(eid, {}),
                        }
                    )
                return out
            except Exception:
                pass
        scored: List[Tuple[float, str]] = []
        for eid, vec in zip(self._ids, self._vectors):
            scored.append((_cosine(q, vec), eid))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"id": eid, "score": score, "metadata": self._meta.get(eid, {})}
            for score, eid in scored[:k]
        ]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
