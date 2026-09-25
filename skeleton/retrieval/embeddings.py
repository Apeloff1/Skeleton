"""Local embeddings — deterministic hash vectors for semantic-ish rerank.

No external model: text maps to a unit-normalised hashing vector over a
fixed dimension, similarity is a cosine dot. The retrieval Ranker can
blend fused score with embedding similarity without an API call.

- :class:`LocalEmbedder` — vector() + similarity()
- :func:`rerank_by_embedding` — blend similarity into fused score
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult

_TOKEN = re.compile(r"[a-z0-9]+")


class LocalEmbedder:
    """Deterministic bag-of-words hashing embedder."""

    def __init__(self, *, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    def vector(self, text: str) -> Tuple[float, ...]:
        tokens = _TOKEN.findall((text or "").lower())
        vec = [0.0] * self._dim
        for token in tokens:
            digest = hashlib.sha256(token.encode()).digest()
            idx = digest[0] % self._dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return tuple(v / norm for v in vec)

    def similarity(self, a: Sequence[float], b: Sequence[float]) -> float:
        if len(a) != len(b):
            raise ValueError("embedding dimensions differ")
        return sum(x * y for x, y in zip(a, b))



def _embed_text(item: ScoredResult) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    raw = metadata.get("text") or metadata.get("preview") or ""
    if isinstance(raw, str) and raw.strip():
        return raw
    if isinstance(item.content, str) and item.content.strip():
        return item.content
    return item.fragment_id


def rerank_by_embedding(
    embedder: LocalEmbedder,
    query: str,
    items: Sequence[ScoredResult],
    *,
    weight: float = 0.3,
) -> Tuple[ScoredResult, ...]:
    """Blend embedding similarity (weight) with fused score into the final."""
    query_vec = embedder.vector(query)
    scored = []
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0.0 <= float(weight) <= 1.0:
        raise ValueError("weight must be between 0 and 1")
    for item in items:
        text = _embed_text(item)
        sim = embedder.similarity(query_vec, embedder.vector(text))
        scored.append((item, sim))
    scored.sort(key=lambda kv: -(kv[1] * weight + kv[0].score * (1.0 - weight)))
    return tuple(
        ScoredResult(
            fragment_id=item.fragment_id,
            content=item.content,
            score=round(item.score * (1.0 - weight) + sim * weight, 6),
            plane=item.plane,
            provenance=item.provenance,
            metadata=dict(item.metadata),
        )
        for item, sim in scored
    )
