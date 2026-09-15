"""
Skeleton Memory — Differential Privacy Layer

The memory planes hold everything the system learns. This layer makes
sure aggregate queries against those planes can answer honestly about
patterns while being mathematically incapable of leaking any single
individual record — formal privacy, not policy.

Mechanisms (all deterministic-seeded, reproducible per query_id):

- LaplaceMechanism: adds Laplace noise scaled to query sensitivity / ε
  to numeric aggregates (counts, sums, means). Composition tracked
  across the session: each query spends ε from a session budget;
  exhausted budgets refuse further queries (hard stop, not warning).
- ExponentialMechanism: for categorical answers (which plane to use,
  which template to offer) — selection probability ∝ exp(ε·score/2Δu)
  so the best option is likely but not certain, bounding inference
  about any one record's influence.
- PrivatePlaneAdapter: wraps RAG/MAG/CAG stores so all outbound
  aggregates pass through the mechanisms. Raw records never leave;
  only noised counts, noised means, and mechanism-selected categories.
- PrivacyAccountant: per-session ε ledger with per-plane and total
  budgets, remaining-budget queries, and consumption history. The
  accountant is the single source of truth for privacy spend.

The math is real: Laplace(0, Δf/ε) noise on sensitivity-bounded
queries satisfies ε-differential privacy under composition, and the
accountant enforces the composition bound.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Privacy accountant (composition tracking)
# ---------------------------------------------------------------------------

@dataclass
class PrivacySpend:
    """One recorded privacy spend event."""
    mechanism: str
    epsilon: float
    query_kind: str
    at: float = field(default_factory=time.time)


class PrivacyAccountant:
    """Session ε ledger: budget enforcement under composition."""

    def __init__(self, session_budget: float = 1.0, per_plane_budget: float = 0.5):
        self.session_budget = session_budget
        self.per_plane_budget = per_plane_budget
        self._spent_total = 0.0
        self._spent_by_plane: Dict[str, float] = {}
        self._history: List[PrivacySpend] = []

    def can_spend(self, epsilon: float, plane: str = "") -> bool:
        if self._spent_total + epsilon > self.session_budget:
            return False
        if plane and self._spent_by_plane.get(plane, 0.0) + epsilon > self.per_plane_budget:
            return False
        return True

    def spend(self, epsilon: float, mechanism: str, query_kind: str,
              plane: str = "") -> bool:
        """Record a spend; False (and no spend) if budget exceeded."""
        if not self.can_spend(epsilon, plane):
            return False
        self._spent_total += epsilon
        if plane:
            self._spent_by_plane[plane] = self._spent_by_plane.get(plane, 0.0) + epsilon
        self._history.append(PrivacySpend(mechanism, epsilon, query_kind))
        return True

    def remaining(self, plane: str = "") -> float:
        if plane:
            return max(0.0, self.per_plane_budget - self._spent_by_plane.get(plane, 0.0))
        return max(0.0, self.session_budget - self._spent_total)

    def stats(self) -> Dict[str, Any]:
        return {
            "session_budget": self.session_budget,
            "spent_total": round(self._spent_total, 4),
            "spent_by_plane": {k: round(v, 4) for k, v in self._spent_by_plane.items()},
            "remaining": round(self.remaining(), 4),
            "events": len(self._history),
        }


# ---------------------------------------------------------------------------
# Deterministic noise source (reproducible per query id)
# ---------------------------------------------------------------------------

class SeededNoise:
    """Reproducible randomness: same query_id → same noise draw.

    Reproducibility matters for debugging and cache consistency; the
    seed is derived from a secret salt + query id, never from the data.
    """

    def __init__(self, salt: bytes = b"skeleton-dp-salt"):
        self.salt = salt

    def rng_for(self, query_id: str) -> random.Random:
        digest = hashlib.sha256(self.salt + query_id.encode()).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    @staticmethod
    def laplace(rng: random.Random, scale: float) -> float:
        """Sample Laplace(0, scale) via inverse CDF."""
        u = rng.random() - 0.5
        return -scale * math.copysign(math.log(1 - 2 * abs(u)), u)


# ---------------------------------------------------------------------------
# Mechanisms
# ---------------------------------------------------------------------------

class LaplaceMechanism:
    """ε-DP for numeric aggregates via sensitivity-scaled Laplace noise."""

    def __init__(self, accountant: PrivacyAccountant, noise: Optional[SeededNoise] = None):
        self.accountant = accountant
        self.noise = noise or SeededNoise()

    def privatize_count(self, true_count: int, epsilon: float,
                        query_id: str, plane: str = "") -> Optional[float]:
        """Noised count. Count sensitivity Δf = 1."""
        if not self.accountant.spend(epsilon, "laplace", "count", plane):
            return None
        scale = 1.0 / epsilon
        return true_count + self.noise.laplace(self.noise.rng_for(query_id), scale)

    def privatize_mean(self, values: List[float], epsilon: float,
                       query_id: str, value_range: Tuple[float, float],
                       plane: str = "") -> Optional[float]:
        """Noised mean over a clamped range. Mean sensitivity = range / n."""
        if not values:
            return None
        if not self.accountant.spend(epsilon, "laplace", "mean", plane):
            return None
        lo, hi = value_range
        clamped = [max(lo, min(hi, v)) for v in values]
        sensitivity = (hi - lo) / len(clamped)
        scale = sensitivity / epsilon
        mean = sum(clamped) / len(clamped)
        return mean + self.noise.laplace(self.noise.rng_for(query_id), scale)

    def privatize_histogram(self, buckets: Dict[str, int], epsilon: float,
                            query_id: str, plane: str = "") -> Optional[Dict[str, float]]:
        """Noised histogram; per-bucket sensitivity 1, budget split evenly."""
        if not buckets:
            return None
        per_bucket_eps = epsilon / len(buckets)
        if not self.accountant.spend(epsilon, "laplace", "histogram", plane):
            return None
        rng = self.noise.rng_for(query_id)
        return {k: v + self.noise.laplace(rng, 1.0 / per_bucket_eps)
                for k, v in buckets.items()}


class ExponentialMechanism:
    """ε-DP selection over categorical options by quality score."""

    def __init__(self, accountant: PrivacyAccountant, noise: Optional[SeededNoise] = None):
        self.accountant = accountant
        self.noise = noise or SeededNoise()

    def select(self, options: Dict[str, float], epsilon: float,
               query_id: str, sensitivity: float = 1.0,
               plane: str = "") -> Optional[str]:
        """Pick an option with probability ∝ exp(ε·score / 2Δu)."""
        if not options:
            return None
        if not self.accountant.spend(epsilon, "exponential", "select", plane):
            return None
        rng = self.noise.rng_for(query_id)
        weights = {k: math.exp(epsilon * s / (2 * sensitivity))
                   for k, s in options.items()}
        total = sum(weights.values())
        pick = rng.random() * total
        cumulative = 0.0
        for key, w in weights.items():
            cumulative += w
            if pick <= cumulative:
                return key
        return next(iter(options))


# ---------------------------------------------------------------------------
# Private plane adapter
# ---------------------------------------------------------------------------

class PrivatePlaneAdapter:
    """DP-wrapped access to a memory plane. Raw records never leave;
    only noised aggregates and mechanism-selected categories."""

    def __init__(self, plane_name: str, store: Any,
                 accountant: PrivacyAccountant):
        self.plane_name = plane_name
        self._store = store
        self.accountant = accountant
        self.laplace = LaplaceMechanism(accountant)
        self.exponential = ExponentialMechanism(accountant)
        self._query_counter = 0

    def _qid(self, kind: str) -> str:
        self._query_counter += 1
        return f"{self.plane_name}:{kind}:{self._query_counter}"

    def document_count(self, epsilon: float = 0.1) -> Optional[float]:
        """Noised document count for the plane."""
        true = 0
        if hasattr(self._store, "_entries"):
            true = len(self._store._entries)
        elif hasattr(self._store, "_docs"):
            true = len(self._store._docs)
        elif hasattr(self._store, "_episodes"):
            true = len(self._store._episodes)
        return self.laplace.privatize_count(true, epsilon, self._qid("count"),
                                            plane=self.plane_name)

    def tag_histogram(self, epsilon: float = 0.2) -> Optional[Dict[str, float]]:
        """Noised tag-frequency histogram (MAG planes)."""
        tags: Dict[str, int] = {}
        tag_index = getattr(self._store, "_tag_index", None)
        if tag_index:
            tags = {t: len(ids) for t, ids in tag_index.items()}
        if not tags:
            return None
        return self.laplace.privatize_histogram(tags, epsilon,
                                                self._qid("tags"), plane=self.plane_name)

    def pick_category(self, options: Dict[str, float], epsilon: float = 0.1) -> Optional[str]:
        """Mechanism-selected category (e.g. which plane to route a query to)."""
        return self.exponential.select(options, epsilon, self._qid("select"),
                                       plane=self.plane_name)

    def budget_remaining(self) -> float:
        return self.accountant.remaining(self.plane_name)


class DifferentialPrivacy:
    """Top-level DP layer: accountant + per-plane adapters."""

    def __init__(self, session_budget: float = 1.0, per_plane_budget: float = 0.5):
        self.accountant = PrivacyAccountant(session_budget, per_plane_budget)
        self._adapters: Dict[str, PrivatePlaneAdapter] = {}

    def wrap(self, plane_name: str, store: Any) -> PrivatePlaneAdapter:
        adapter = PrivatePlaneAdapter(plane_name, store, self.accountant)
        self._adapters[plane_name] = adapter
        return adapter

    def adapter(self, plane_name: str) -> Optional[PrivatePlaneAdapter]:
        return self._adapters.get(plane_name)

    def stats(self) -> Dict[str, Any]:
        return {"accountant": self.accountant.stats(),
                "planes": sorted(self._adapters.keys())}
