"""Shadow mode — silent A/B testing — split from resilience_extended (v16.2)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus

# =============================================================================
# SHADOW MODE — SILENT A/B TESTING
# =============================================================================

@dataclass
class ShadowExperiment:
    experiment_id: str
    variant_a: str
    variant_b: str
    traffic_split: float = 0.1
    metrics: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    active: bool = True


class ShadowMode:
    """
    Silent A/B testing infrastructure.
    Runs variant B in shadow (non-user-visible) while serving variant A.
    Collects metrics without impacting user experience.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._experiments: Dict[str, ShadowExperiment] = {}
        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._bus = bus

    def create_experiment(
        self,
        experiment_id: str,
        variant_a: str,
        variant_b: str,
        traffic_split: float = 0.1,
        metrics: Optional[List[str]] = None,
    ) -> ShadowExperiment:
        exp = ShadowExperiment(
            experiment_id=experiment_id,
            variant_a=variant_a,
            variant_b=variant_b,
            traffic_split=traffic_split,
            metrics=metrics or ["latency", "quality_score", "token_count"],
        )
        self._experiments[experiment_id] = exp
        self._results[experiment_id] = []
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="shadow.experiment.created",
                    payload={
                        "experiment_id": experiment_id,
                        "variant_a": variant_a,
                        "variant_b": variant_b,
                        "traffic_split": traffic_split,
                    },
                    correlation_id=f"shadow_{experiment_id}",
                )
            )
        return exp

    def should_shadow(self, experiment_id: str, user_id: str) -> bool:
        if experiment_id not in self._experiments:
            return False
        exp = self._experiments[experiment_id]
        if not exp.active:
            return False
        hash_input = f"{experiment_id}:{user_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        return (hash_value % 10000) / 10000 < exp.traffic_split

    def record_shadow_result(
        self,
        experiment_id: str,
        user_id: str,
        variant_a_result: Dict[str, Any],
        variant_b_result: Dict[str, Any],
    ) -> None:
        if experiment_id not in self._experiments:
            return
        record = {
            "timestamp": time.time(),
            "user_id": user_id,
            "variant_a": variant_a_result,
            "variant_b": variant_b_result,
            "differences": {
                k: variant_b_result.get(k, 0) - variant_a_result.get(k, 0)
                for k in self._experiments[experiment_id].metrics
                if k in variant_a_result and k in variant_b_result
            },
        }
        self._results[experiment_id].append(record)

    def get_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        if experiment_id not in self._results:
            return {"error": "Experiment not found"}
        results = self._results[experiment_id]
        if not results:
            return {"experiment_id": experiment_id, "samples": 0}

        stats: Dict[str, Dict[str, float]] = {}
        for metric in self._experiments[experiment_id].metrics:
            diffs = [r["differences"].get(metric, 0) for r in results if metric in r["differences"]]
            if diffs:
                stats[metric] = {
                    "mean_diff": sum(diffs) / len(diffs),
                    "min_diff": min(diffs),
                    "max_diff": max(diffs),
                    "samples": len(diffs),
                }

        return {
            "experiment_id": experiment_id,
            "samples": len(results),
            "duration_hours": (time.time() - self._experiments[experiment_id].start_time) / 3600,
            "statistics": stats,
        }

    def end_experiment(self, experiment_id: str) -> Optional[ShadowExperiment]:
        if experiment_id not in self._experiments:
            return None
        exp = self._experiments[experiment_id]
        exp.active = False
        exp.end_time = time.time()
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="shadow.experiment.ended",
                    payload={
                        "experiment_id": experiment_id,
                        "duration_hours": (exp.end_time - exp.start_time) / 3600,
                        "total_samples": len(self._results.get(experiment_id, [])),
                    },
                    correlation_id=f"shadow_{experiment_id}",
                )
            )
        return exp
