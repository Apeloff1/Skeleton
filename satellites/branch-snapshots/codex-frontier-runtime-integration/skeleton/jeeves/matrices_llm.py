"""
Skeleton Jeeves — Memory matrices

Provides the three Jeeves matrices surfaced at /jeeves/matrices:

- SAM  (Semantic Association Map): co-occurrence graph over terms
        observed in conversation; supports association lookups that
        prime retrieval beyond the raw query text.
- CLOM (Compressed Learned Outcome Model): rolling per-intent
        outcome statistics — what worked, for which kind of request.
- KREM (Knowledge Retention Matrix): per-concept retention estimate
        with spaced-repetition decay; flags what needs refreshing.

Each matrix exposes `observe(...)`, `snapshot()`, and `stats()`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


class SemanticAssociationMap:
    """Co-occurrence graph over conversation terms.

    Terms appearing in the same turn become associated; edges decay
    so stale associations fade. Used to expand queries with
    associated terms before hitting the retrieval planes.
    """

    DECAY = 0.98

    def __init__(self):
        self._edges: Dict[str, Dict[str, float]] = {}
        self._stats = {"turns": 0}

    def observe(self, text: str) -> None:
        """Record term co-occurrences from a turn of text."""
        terms = self._terms(text)
        self._stats["turns"] += 1
        for i, a in enumerate(terms):
            for b in terms[i + 1:]:
                self._bump(a, b)
                self._bump(b, a)

    def associations(self, term: str, top_k: int = 5) -> List[tuple]:
        """Top associated terms for a query term."""
        edges = self._edges.get(term.lower(), {})
        ranked = sorted(edges.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def expand(self, query: str, top_k: int = 3) -> List[str]:
        """Expand a query with its strongest associations."""
        expansions: Set[str] = set()
        for term in self._terms(query):
            for assoc, _ in self.associations(term, top_k=top_k):
                expansions.add(assoc)
        return sorted(expansions - set(self._terms(query)))

    def decay(self) -> None:
        """Fade all edge weights; prune the near-zero."""
        for a in list(self._edges.keys()):
            for b in list(self._edges[a].keys()):
                self._edges[a][b] *= self.DECAY
                if self._edges[a][b] < 0.01:
                    del self._edges[a][b]
            if not self._edges[a]:
                del self._edges[a]

    def _bump(self, a: str, b: str) -> None:
        self._edges.setdefault(a, {})[b] = self._edges.get(a, {}).get(b, 0.0) + 1.0

    @staticmethod
    def _terms(text: str) -> List[str]:
        words = [w.lower().strip(".,!?;:()[]{}\"'") for w in text.split()]
        return sorted({w for w in words if len(w) > 3})

    def snapshot(self) -> Dict[str, Any]:
        top = sorted(
            ((a, b, w) for a, es in self._edges.items() for b, w in es.items()),
            key=lambda x: x[2], reverse=True,
        )[:10]
        return {
            "terms": len(self._edges),
            "edges": sum(len(es) for es in self._edges.values()),
            "strongest": [{"from": a, "to": b, "weight": round(w, 3)} for a, b, w in top],
        }

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "terms": len(self._edges)}


@dataclass
class OutcomeRecord:
    intent: str
    success: bool
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


class CompressedLearnedOutcomeModel:
    """Rolling per-intent outcome statistics.

    Tracks success rate and latency per intent category so Jeeves
    can route requests to the strategy that historically worked,
    and surface degraded intents before users notice.
    """

    def __init__(self, window: int = 200):
        self._window = window
        self._records: Dict[str, List[OutcomeRecord]] = {}

    def observe(self, intent: str, success: bool, latency_ms: float = 0.0) -> None:
        records = self._records.setdefault(intent, [])
        records.append(OutcomeRecord(intent=intent, success=success, latency_ms=latency_ms))
        if len(records) > self._window:
            self._records[intent] = records[-self._window:]

    def success_rate(self, intent: str) -> Optional[float]:
        records = self._records.get(intent, [])
        if not records:
            return None
        return sum(1 for r in records if r.success) / len(records)

    def best_intent(self) -> Optional[str]:
        rates = {i: self.success_rate(i) for i in self._records if self._records[i]}
        rates = {i: r for i, r in rates.items() if r is not None}
        return max(rates, key=rates.get) if rates else None

    def degraded(self, threshold: float = 0.5, min_samples: int = 5) -> List[str]:
        """Intents with enough data but poor recent outcomes."""
        out = []
        for intent, records in self._records.items():
            if len(records) >= min_samples:
                rate = self.success_rate(intent)
                if rate is not None and rate < threshold:
                    out.append(intent)
        return out

    def snapshot(self) -> Dict[str, Any]:
        return {
            "intents": {
                intent: {
                    "samples": len(records),
                    "success_rate": round(self.success_rate(intent) or 0.0, 3),
                    "avg_latency_ms": round(sum(r.latency_ms for r in records) / len(records), 1),
                }
                for intent, records in self._records.items()
            },
            "degraded": self.degraded(),
        }

    def stats(self) -> Dict[str, Any]:
        return {"intents": len(self._records), "records": sum(len(r) for r in self._records.values())}


@dataclass
class RetentionCell:
    concept: str
    strength: float = 1.0
    reviews: int = 0
    last_seen: float = field(default_factory=time.time)


class KnowledgeRetentionMatrix:
    """Per-concept retention estimate with spaced decay.

    Concepts start at strength 1.0 and decay with a half-life;
    re-observation refreshes and strengthens them. `due()` returns
    concepts whose retention has fallen below threshold — the
    refresh list that pairs with the RepetitionScheduler.
    """

    HALF_LIFE_HOURS = 72.0
    DUE_THRESHOLD = 0.4

    def __init__(self):
        self._cells: Dict[str, RetentionCell] = {}

    def observe(self, concept: str) -> None:
        cell = self._cells.get(concept)
        if cell is None:
            self._cells[concept] = RetentionCell(concept=concept)
        else:
            cell.strength = min(2.0, self._retained(cell) + 0.3)
            cell.reviews += 1
            cell.last_seen = time.time()

    def retention(self, concept: str) -> float:
        cell = self._cells.get(concept)
        return self._retained(cell) if cell else 0.0

    def due(self, threshold: Optional[float] = None) -> List[str]:
        """Concepts whose retention fell below the refresh threshold."""
        cut = threshold if threshold is not None else self.DUE_THRESHOLD
        return [c for c, cell in self._cells.items() if self._retained(cell) < cut]

    def _retained(self, cell: RetentionCell) -> float:
        elapsed_hours = (time.time() - cell.last_seen) / 3600.0
        decay = math.pow(0.5, elapsed_hours / self.HALF_LIFE_HOURS)
        return cell.strength * decay

    def snapshot(self) -> Dict[str, Any]:
        weakest = sorted(self._cells.values(), key=self._retained)[:10]
        return {
            "concepts": len(self._cells),
            "due_count": len(self.due()),
            "weakest": [
                {"concept": c.concept, "retention": round(self._retained(c), 3), "reviews": c.reviews}
                for c in weakest
            ],
        }

    def stats(self) -> Dict[str, Any]:
        return {"concepts": len(self._cells), "due": len(self.due())}
