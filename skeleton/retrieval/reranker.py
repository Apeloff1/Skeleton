"""FeatureReranker — the second pass that fusion retrieval is missing.

Fusion (the quad lattice) is a *first* pass: fast, broad, approximate.
Its scores come from per-tier heuristics that never look at the query and
the document *together*. The reranker is the second pass: it re-scores
the top-N fused candidates using features of the query–document pair
itself, and returns a reordered list.

Features (all computed locally, no external model):
  - exact-term coverage: fraction of query terms present in the chunk
  - term proximity: how tightly matched terms cluster in the document
  - position bias: matches near the document head score higher
  - length normalisation: BM25-style penalty so long chunks can't win
    by sheer term stuffing
  - first-pass score: the fusion contribution, carried as one feature

Weights are explicit and tunable; the default ordering is principled
(coverage dominates) rather than tuned to a benchmark. Deterministic
given the same inputs; pure domain, no I/O.

Naming: this module previously exported a class named ``Reranker``, which
collided with the rule-based ``Reranker`` in ``rerank.py``. Renamed to
:class:`FeatureReranker`; a ``Reranker`` alias remains at module bottom
so legacy direct importers (``genesis.py`` pre-migration) keep resolving.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


@dataclass(frozen=True)
class RerankWeights:
    coverage: float = 0.40
    proximity: float = 0.20
    position: float = 0.15
    length_norm: float = 0.05
    first_pass: float = 0.20


@dataclass(frozen=True)
class RankedItem:
    """One reranked candidate with its feature breakdown."""
    item_id: str
    text: str
    metadata: Dict[str, Any]
    score: float
    features: Dict[str, float]
    original_score: float
    original_rank: int


class FeatureReranker:
    """Feature-based second-pass reranker."""

    def __init__(self, *, weights: RerankWeights = RerankWeights(),
                 avg_doc_len: float = 400.0) -> None:
        self.weights = weights
        self.avg_doc_len = avg_doc_len
        self._queries = 0

    def rerank(
        self,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        *,
        top_k: int = 10,
    ) -> List[RankedItem]:
        """
        Reorder candidates. Each candidate is a dict with keys:
        ``id``/``item_id``, ``text``, optional ``metadata``, optional
        ``score`` (first-pass) and ``rank``.
        """
        terms = self._terms(query)
        ranked: List[RankedItem] = []
        for i, cand in enumerate(candidates):
            text = str(cand.get("text", ""))
            doc_terms = self._terms(text)
            features = {
                "coverage": self._coverage(terms, doc_terms),
                "proximity": self._proximity(terms, text),
                "position": self._position(terms, text),
                "length_norm": self._length_norm(len(doc_terms)),
                "first_pass": float(cand.get("score", 0.0)),
            }
            w = self.weights
            score = (
                w.coverage * features["coverage"]
                + w.proximity * features["proximity"]
                + w.position * features["position"]
                + w.length_norm * features["length_norm"]
                + w.first_pass * features["first_pass"]
            )
            ranked.append(RankedItem(
                item_id=str(cand.get("id", cand.get("item_id", f"cand_{i}"))),
                text=text,
                metadata=dict(cand.get("metadata", {})),
                score=score,
                features=features,
                original_score=float(cand.get("score", 0.0)),
                original_rank=int(cand.get("rank", i + 1)),
            ))
        ranked.sort(key=lambda r: r.score, reverse=True)
        self._queries += 1
        return ranked[:top_k]

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    def _terms(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())

    def _coverage(self, terms: List[str], doc_terms: List[str]) -> float:
        if not terms:
            return 0.0
        doc_set = set(doc_terms)
        return len(set(terms) & doc_set) / len(set(terms))

    def _proximity(self, terms: List[str], text: str) -> float:
        """1 / (1 + mean pairwise distance of matched terms, in words)."""
        lowered = text.lower()
        positions: List[int] = []
        word_offset = 0
        for word in lowered.split():
            if any(t in word for t in set(terms)):
                positions.append(word_offset)
            word_offset += 1
        if len(positions) < 2:
            return 1.0 if len(positions) == 1 else 0.0
        span = max(positions) - min(positions)
        return 1.0 / (1.0 + span)

    def _position(self, terms: List[str], text: str) -> float:
        """Earlier first-match scores higher (decays over ~100 words)."""
        lowered = text.lower()
        first = None
        for i, word in enumerate(lowered.split()):
            if any(t in word for t in set(terms)):
                first = i
                break
        if first is None:
            return 0.0
        return math.exp(-first / 100.0)

    def _length_norm(self, doc_len: int) -> float:
        """BM25-flavoured length normalisation centred on avg_doc_len."""
        k1, b = 1.2, 0.75
        norm = 1 - b + b * (doc_len / max(self.avg_doc_len, 1.0))
        return k1 / (k1 + norm)

    def stats(self) -> Dict[str, Any]:
        return {"queries_reranked": self._queries,
                "weights": self.weights.__dict__}


# ----------------------------------------------------------------------
# Legacy alias — direct importers (``from skeleton.retrieval.reranker
# import Reranker``) keep resolving while callers migrate to the clear
# :class:`FeatureReranker` name. ``rerank.py`` owns the ``Reranker`` name
# (rule-based boosting) and is the root-package export.
# ----------------------------------------------------------------------
Reranker = FeatureReranker
