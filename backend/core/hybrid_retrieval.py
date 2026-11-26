"""Hybrid lexical + dense retrieval with reciprocal-rank fusion and a local fallback.

* :class:`Bm25` is Okapi BM25 over the shared tokenizer, with IDF, so rare terms
  outweigh common ones. Plain keyword overlap treats every term equally.
* :class:`Embedder` is a protocol for dense encoders. :class:`HashingEmbedder` is
  the always-available **local fallback**: signed feature hashing of word
  unigrams/bigrams and character trigrams into an L2-normalised vector. It is
  deterministic, needs no model, network or credentials, and tolerates
  morphology and typos ("checkpoint" ~ "checkpoints", "renderer" ~ "rendering").
* :class:`FallbackEmbedder` wraps a provider embedder. If the provider raises or
  returns a malformed vector, the query falls back to the local space. Vectors
  from different spaces are never compared: every document always has a local
  vector, and provider vectors are kept per embedder ``name``.
* :func:`rrf_fuse` is Reciprocal Rank Fusion (Cormack et al., 2009). It
  combines the lexical and dense rankings without score calibration.

Everything is pure Python and deterministic for a given input.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_STOPWORDS = frozenset("a an and are as at be but by for from in is it of on or that the this to was were with".split())
RRF_K = 60


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if len(t) > 1 and t not in _STOPWORDS]


class Bm25:
    """Okapi BM25 over a fixed corpus (rebuild when the corpus changes)."""

    def __init__(self, documents: Mapping[str, str], *, k1: float = 1.2, b: float = 0.75) -> None:
        if k1 < 0 or not 0.0 <= b <= 1.0:
            raise ValueError("invalid BM25 parameters")
        self.k1, self.b = k1, b
        self._tf: dict[str, Counter[str]] = {doc_id: Counter(tokens(text)) for doc_id, text in documents.items()}
        self._len = {doc_id: sum(tf.values()) for doc_id, tf in self._tf.items()}
        self._avg = (sum(self._len.values()) / len(self._len)) if self._len else 0.0
        df: Counter[str] = Counter()
        for tf in self._tf.values():
            df.update(tf.keys())
        n = len(self._tf)
        self._idf = {term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def scores(self, query: str) -> dict[str, float]:
        terms = [t for t in dict.fromkeys(tokens(query)) if t in self._idf]
        out: dict[str, float] = {}
        if not terms or not self._avg:
            return out
        for doc_id, tf in self._tf.items():
            norm = self.k1 * (1.0 - self.b + self.b * self._len[doc_id] / self._avg)
            score = 0.0
            for term in terms:
                f = tf.get(term, 0)
                if f:
                    score += self._idf[term] * f * (self.k1 + 1.0) / (f + norm)
            if score > 0.0:
                out[doc_id] = score
        return out


@runtime_checkable
class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm > 0 else vector


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@dataclass(frozen=True)
class HashingEmbedder:
    """Deterministic local embedder: signed hashing of words, bigrams and char trigrams."""

    dim: int = 512
    name: str = field(default="local-hashing-v1")

    def __post_init__(self) -> None:
        if self.dim < 16:
            raise ValueError("dim must be >= 16")

    def _features(self, text: str) -> Counter[str]:
        words = tokens(text)
        feats: Counter[str] = Counter()
        for word in words:
            feats[f"w:{word}"] += 2
            padded = f"#{word}#"
            for i in range(len(padded) - 2):
                feats[f"c:{padded[i : i + 3]}"] += 1
        for left, right in zip(words, words[1:], strict=False):
            feats[f"b:{left}_{right}"] += 1
        return feats

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            for feature, weight in self._features(text).items():
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign * (1.0 + math.log(weight))
            out.append(_normalise(vector))
        return out


class FallbackEmbedder:
    """Try ``primary``; on error or malformed output, report failure so callers use local."""

    def __init__(self, primary: Embedder, *, on_error: Callable[[BaseException], None] | None = None) -> None:
        self.primary = primary
        self.name = primary.name
        self._on_error = on_error
        self.failures = 0

    def try_embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        try:
            vectors = self.primary.embed(list(texts))
            if len(vectors) != len(texts):
                raise ValueError("embedder returned the wrong number of vectors")
            dims = {len(v) for v in vectors}
            if len(dims) > 1 or 0 in dims:
                raise ValueError("embedder returned inconsistent dimensions")
            if not all(math.isfinite(x) for v in vectors for x in v):
                raise ValueError("embedder returned non-finite values")
            return [_normalise([float(x) for x in v]) for v in vectors]
        except Exception as exc:  # provider outages must degrade, not fail retrieval
            self.failures += 1
            if self._on_error is not None:
                self._on_error(exc)
            return None


def rrf_fuse(rankings: Sequence[Sequence[str]], *, k: int = RRF_K) -> dict[str, float]:
    if k < 1:
        raise ValueError("k must be >= 1")
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


@dataclass(frozen=True)
class HybridHit:
    doc_id: str
    fused: float
    relevance: float
    lexical_rank: int | None
    dense_rank: int | None
    dense_space: str


class HybridIndex:
    """In-memory hybrid index. Documents are (id -> text); rebuilds BM25 lazily."""

    def __init__(
        self,
        *,
        local: HashingEmbedder | None = None,
        provider: FallbackEmbedder | None = None,
        dense_floor: float = 0.05,
        rrf_k: int = RRF_K,
    ) -> None:
        self._local = local or HashingEmbedder()
        self._provider = provider
        self._docs: dict[str, str] = {}
        self._vectors: dict[str, dict[str, list[float]]] = {}
        self._bm25: Bm25 | None = None
        self._dense_floor = dense_floor
        self._rrf_k = rrf_k

    def __len__(self) -> int:
        return len(self._docs)

    def upsert(self, doc_id: str, text: str) -> None:
        if not doc_id:
            raise ValueError("doc_id is required")
        self._docs[doc_id] = text
        spaces = {self._local.name: self._local.embed([text])[0]}
        if self._provider is not None:
            vectors = self._provider.try_embed([text])
            if vectors is not None:
                spaces[self._provider.name] = vectors[0]
        self._vectors[doc_id] = spaces
        self._bm25 = None

    def remove(self, doc_id: str) -> bool:
        existed = self._docs.pop(doc_id, None) is not None
        self._vectors.pop(doc_id, None)
        if existed:
            self._bm25 = None
        return existed

    def _query_vector(self) -> Callable[[str], tuple[str, list[float]]]:
        def encode(query: str) -> tuple[str, list[float]]:
            if self._provider is not None:
                vectors = self._provider.try_embed([query])
                if vectors is not None:
                    return self._provider.name, vectors[0]
            return self._local.name, self._local.embed([query])[0]

        return encode

    def search(self, query: str, *, limit: int = 10, allow: Callable[[str], bool] | None = None) -> list[HybridHit]:
        if limit < 1 or not self._docs or not tokens(query):
            return []
        candidates = [d for d in self._docs if allow is None or allow(d)]
        if not candidates:
            return []
        if self._bm25 is None:
            self._bm25 = Bm25(self._docs)
        lexical_scores = self._bm25.scores(query)
        lexical = sorted((d for d in candidates if d in lexical_scores), key=lambda d: (-lexical_scores[d], d))
        space, qvec = self._query_vector()(query)
        dense_scores: dict[str, float] = {}
        for doc_id in candidates:
            vector = self._vectors[doc_id].get(space)
            if vector is not None and len(vector) == len(qvec):
                similarity = cosine(qvec, vector)
                if similarity >= self._dense_floor:
                    dense_scores[doc_id] = similarity
        dense = sorted(dense_scores, key=lambda d: (-dense_scores[d], d))
        fused = rrf_fuse([lexical, dense], k=self._rrf_k)
        ceiling = 2.0 / (self._rrf_k + 1)
        lex_rank = {d: i for i, d in enumerate(lexical, start=1)}
        den_rank = {d: i for i, d in enumerate(dense, start=1)}
        ordered = sorted(fused, key=lambda d: (-fused[d], d))[:limit]
        return [
            HybridHit(
                doc_id=d,
                fused=fused[d],
                relevance=min(1.0, fused[d] / ceiling),
                lexical_rank=lex_rank.get(d),
                dense_rank=den_rank.get(d),
                dense_space=space,
            )
            for d in ordered
        ]


__all__ = [
    "Bm25",
    "Embedder",
    "FallbackEmbedder",
    "HashingEmbedder",
    "HybridHit",
    "HybridIndex",
    "cosine",
    "rrf_fuse",
    "tokens",
]
