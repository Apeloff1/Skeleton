"""Workflow-aware filler eviction — KVFlow-flavored cache pressure policy.

Ported insight from KVFlow (workflow-aware prefix-cache eviction for
multi-agent LLM workflows): when the filler store is full, don't evict the
global LRU — evict the filler whose loss costs the least *workflow* damage.
Cost proxy per filler:

    keep_score = (hits-weighted recency) + freshness + rebuild cost

where rebuild cost is token count (rebuilding a 40k-token prefix hurts more
than a 200-token one), recency is time since last refresh, and hits come
from the caller's PrefixRegistry when supplied.

Pure domain. ``FillerStore.evict_for_capacity`` is additive; nothing else
changes.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from .warmer import Filler, FillerStore


def keep_score(
    filler: Filler,
    *,
    now: Optional[float] = None,
    hits: int = 0,
) -> float:
    """Higher = more painful to evict."""
    now = now if now is not None else time.time()
    age_s = max(0.0, now - filler.refreshed_at)
    recency = 1.0 / (1.0 + age_s / 3600.0)          # decays hourly
    freshness = 1.0 if filler.is_fresh(now) else 0.2
    rebuild_cost = min(4.0, filler.tokens / 10_000)  # 40k tokens → 4.0 cap
    hit_bonus = min(2.0, hits / 10.0)                # hot prefixes stick
    return recency + freshness + rebuild_cost + hit_bonus


def evict_for_capacity(
    store: FillerStore,
    *,
    capacity: int,
    now: Optional[float] = None,
    hit_counts: Optional[Dict[str, int]] = None,
) -> list:
    """Evict lowest-keep-score fillers until ``len(store) <= capacity``.

    Returns the evicted filler keys. Deterministic: ties break on key name.
    """
    hits = hit_counts or {}
    evicted = []
    while len(store.all()) > capacity:
        victim = min(
            store.all(),
            key=lambda f: (keep_score(f, now=now, hits=hits.get(f.key, 0)), f.key),
        )
        store._fillers.pop(victim.key, None)
        evicted.append(victim.key)
    if evicted:
        store._save()
    return evicted
