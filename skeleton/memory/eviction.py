"""Workflow-aware filler eviction.

When the filler store is over capacity, evict the prefix whose loss costs
the least: low recency, stale, cheap to rebuild, and rarely hit. Ties break
on the key. The store is changed through ``discard``, not by editing its
private table.
"""

from __future__ import annotations

import math
import time
from typing import Dict, Optional

from .warmer import Filler, FillerStore


class EvictionError(ValueError):
    """The eviction request cannot be applied safely."""


def keep_score(
    filler: Filler,
    *,
    now: Optional[float] = None,
    hits: int = 0,
) -> float:
    """Higher means the filler is more expensive to lose."""

    if now is None:
        now = time.time()
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(float(now)):
        raise EvictionError("now must be a finite number")
    if isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
        raise EvictionError("hits must be a non-negative integer")
    if isinstance(filler.tokens, bool) or not isinstance(filler.tokens, int) or filler.tokens < 0:
        raise EvictionError("filler tokens must be a non-negative integer")
    age_s = max(0.0, float(now) - filler.refreshed_at)
    recency = 1.0 / (1.0 + age_s / 3600.0)
    freshness = 1.0 if filler.is_fresh(now) else 0.2
    rebuild_cost = min(4.0, filler.tokens / 10_000)
    hit_bonus = min(2.0, hits / 10.0)
    return recency + freshness + rebuild_cost + hit_bonus


def evict_for_capacity(
    store: FillerStore,
    *,
    capacity: int,
    now: Optional[float] = None,
    hit_counts: Optional[Dict[str, int]] = None,
) -> list:
    """Evict the lowest keep-score fillers until the store is within capacity."""

    if not isinstance(store, FillerStore):
        raise TypeError("store must be a FillerStore")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0:
        raise EvictionError("capacity must be a non-negative integer")
    if hit_counts is None:
        hit_counts = {}
    if not isinstance(hit_counts, dict):
        raise TypeError("hit_counts must be a mapping")
    for key, hits in hit_counts.items():
        if not isinstance(key, str) or isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
            raise EvictionError("hit counts must be non-negative integers")
    evicted: list[str] = []
    while len(store.all()) > capacity:
        victim = min(
            store.all(),
            key=lambda filler: (keep_score(filler, now=now, hits=hit_counts.get(filler.key, 0)), filler.key),
        )
        if not store.discard(victim.key, persist=False):
            raise EvictionError(f"filler {victim.key} disappeared during eviction")
        evicted.append(victim.key)
    if evicted:
        store.persist()
    return evicted


__all__ = ["EvictionError", "evict_for_capacity", "keep_score"]
