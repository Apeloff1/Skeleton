"""
Skeleton Memory — Persona drift detection

Provides:
- PersonaDriftDetector: Detect when agent behavior drifts from baseline
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class BehaviorSample:
    """A single behavior observation."""
    timestamp: float
    action: str
    context: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


class PersonaDriftDetector:
    """Detect when agent behavior deviates from established baseline.
    
    Uses statistical anomaly detection on action distributions
    and optional embedding distance metrics.
    """

    def __init__(self, bus: Optional[EventBus] = None, window_size: int = 100):
        self._bus = bus
        self._window_size = window_size
        self._baseline: Dict[str, float] = {}  # action -> frequency
        self._recent: List[BehaviorSample] = []
        self._drift_threshold = 2.0  # standard deviations
        self._stats = {"checks": 0, "drifts_detected": 0}

    def record(self, action: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Record a behavior observation."""
        sample = BehaviorSample(
            timestamp=time.time(),
            action=action,
            context=context or {},
        )
        self._recent.append(sample)
        
        # Trim window
        if len(self._recent) > self._window_size:
            self._recent = self._recent[-self._window_size:]

    def establish_baseline(self, samples: List[str]) -> None:
        """Establish baseline from historical action distribution."""
        from collections import Counter
        counts = Counter(samples)
        total = len(samples)
        self._baseline = {action: count / total for action, count in counts.items()}

    def check_drift(self) -> Optional[Dict[str, Any]]:
        """Check if recent behavior deviates from baseline.
        
        Returns drift report if drift detected, None otherwise.
        """
        if not self._baseline or len(self._recent) < 10:
            return None
        
        self._stats["checks"] += 1
        
        from collections import Counter
        recent_actions = [s.action for s in self._recent]
        recent_counts = Counter(recent_actions)
        recent_total = len(recent_actions)
        
        # Calculate chi-squared-like deviation
        deviations = []
        for action, baseline_freq in self._baseline.items():
            recent_freq = recent_counts.get(action, 0) / recent_total
            if baseline_freq > 0:
                deviation = (recent_freq - baseline_freq) / baseline_freq
                deviations.append(deviation ** 2)
        
        if not deviations:
            return None
        
        # Check if any action significantly deviated
        max_deviation = max(deviations) if deviations else 0
        
        if max_deviation > self._drift_threshold:
            self._stats["drifts_detected"] += 1
            
            drift_report = {
                "detected": True,
                "severity": "high" if max_deviation > 4.0 else "medium",
                "max_deviation": max_deviation,
                "threshold": self._drift_threshold,
                "sample_count": len(self._recent),
                "baseline_actions": len(self._baseline),
            }
            
            if self._bus:
                self._bus.publish(DomainEvent(
                    topic="memory.drift.detected",
                    payload=drift_report,
                ))
            
            return drift_report
        
        return None

    def get_profile(self) -> Dict[str, Any]:
        """Get current behavior profile."""
        from collections import Counter
        if not self._recent:
            return {"status": "no_data"}
        
        recent_actions = [s.action for s in self._recent]
        counts = Counter(recent_actions)
        total = len(recent_actions)
        
        return {
            "total_observations": total,
            "unique_actions": len(counts),
            "action_distribution": {action: count / total for action, count in counts.most_common(10)},
            "baseline_established": bool(self._baseline),
        }

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "window_size": self._window_size,
            "threshold": self._drift_threshold,
            "observations": len(self._recent),
        }
