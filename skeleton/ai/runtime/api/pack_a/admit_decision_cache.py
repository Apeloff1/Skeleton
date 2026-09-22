"""admit_decision_cache — facade over Pack A AdmitDecisionCache."""

from __future__ import annotations

from typing import Optional

from skeleton.kernel.pack_a.tiered_depth import (
    AdmitDecision,
    AdmitDecisionCache,
    AdmitDecisionRecord,
    default_admit_cache,
)
from skeleton.kernel.pack_a.metrics import default_meter


class DecisionCacheFacade:
    def __init__(self, cache: Optional[AdmitDecisionCache] = None) -> None:
        self.cache = cache if cache is not None else default_admit_cache()
        self.meter = default_meter()

    def lookup(
        self, route_class: str, priority: int, path: str
    ) -> Optional[AdmitDecisionRecord]:
        rec = self.cache.get(route_class, priority, path)
        if rec is None:
            self.meter.cache_misses.labels(route_class).inc()
        else:
            self.meter.cache_hits.labels(route_class).inc()
        return rec

    def store(
        self,
        route_class: str,
        priority: int,
        path: str,
        decision: AdmitDecision,
        *,
        ttl_s: Optional[float] = None,
    ) -> AdmitDecisionRecord:
        return self.cache.put(route_class, priority, path, decision, ttl_s=ttl_s)


def cached_admit_outcome(
    route_class: str, priority: int, path: str
) -> Optional[AdmitDecisionRecord]:
    return DecisionCacheFacade().lookup(route_class, priority, path)


__all__ = ["DecisionCacheFacade", "cached_admit_outcome"]
