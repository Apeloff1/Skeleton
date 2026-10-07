"""
Skeleton Organism — Runtime health, config, and feature flags

Provides:
- OrganismState: Central runtime state container
- FeatureFlags: Toggle features at runtime
- HealthMonitor: Continuous health checking
- QualityState: Quality metrics tracking
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class FeatureFlags:
    """Runtime feature toggles."""
    forge_repair: bool = True
    swarm_negotiation: bool = True
    memory_compression: bool = False
    api_hmac_seal: bool = True
    observability_sampling: bool = True
    canary_rollouts: bool = True

    def to_dict(self) -> Dict[str, bool]:
        return {
            "forge_repair": self.forge_repair,
            "swarm_negotiation": self.swarm_negotiation,
            "memory_compression": self.memory_compression,
            "api_hmac_seal": self.api_hmac_seal,
            "observability_sampling": self.observability_sampling,
            "canary_rollouts": self.canary_rollouts,
        }

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        """Load feature flags from environment variables."""
        import os
        return cls(
            forge_repair=os.getenv("SKELETON_FORGE_REPAIR", "true").lower() == "true",
            swarm_negotiation=os.getenv("SKELETON_SWARM_NEGOTIATION", "true").lower() == "true",
            memory_compression=os.getenv("SKELETON_MEMORY_COMPRESSION", "false").lower() == "true",
            api_hmac_seal=os.getenv("SKELETON_API_HMAC_SEAL", "true").lower() == "true",
            observability_sampling=os.getenv("SKELETON_OBSERVABILITY_SAMPLING", "true").lower() == "true",
            canary_rollouts=os.getenv("SKELETON_CANARY_ROLLOUTS", "true").lower() == "true",
        )


@dataclass
class HealthStatus:
    """Snapshot of system health."""
    overall: str = "unknown"
    checks: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "checks": self.checks,
            "last_updated": self.last_updated,
        }


class HealthMonitor:
    """Continuous health monitoring with configurable checks."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._checks: Dict[str, Callable[[], Dict[str, Any]]] = {}
        self._status = HealthStatus()

    def register(self, name: str, check_fn: Callable[[], Dict[str, Any]]) -> None:
        """Register a health check function."""
        self._checks[name] = check_fn

    def check(self) -> HealthStatus:
        """Run all health checks and update status."""
        results = {}
        healthy = True

        for name, check_fn in self._checks.items():
            try:
                result = check_fn()
                results[name] = result
                if isinstance(result, dict) and result.get("healthy") is False:
                    healthy = False
            except Exception as e:
                results[name] = {"healthy": False, "error": str(e)}
                healthy = False

        self._status = HealthStatus(
            overall="healthy" if healthy else "degraded",
            checks=results,
        )

        if self._bus:
            self._bus.emit("organism.health.checked", self._status.to_dict())

        return self._status

    def liveness(self) -> Dict[str, Any]:
        """Quick liveness probe."""
        return {"alive": True, "timestamp": time.time()}

    def readiness(self) -> Dict[str, Any]:
        """Readiness probe including dependency checks."""
        status = self.check()
        return {
            "ready": status.overall == "healthy",
            "status": status.overall,
            "checks": len(status.checks),
        }

    def stats(self) -> Dict[str, Any]:
        return {"checks_registered": len(self._checks), "last_status": self._status.overall}


class QualityState:
    """Track quality metrics across the system."""

    def __init__(self, root: Optional[Path] = None):
        self._metrics: List[Dict[str, Any]] = []
        self._root = root
        self._file = root / "quality.json" if root else None

    def append(self, metric: Dict[str, Any]) -> None:
        """Append a quality metric."""
        metric["timestamp"] = time.time()
        self._metrics.append(metric)
        self._persist()

    def _persist(self) -> None:
        """Persist metrics to disk if root is set."""
        if self._file:
            try:
                self._file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._file, "w") as f:
                    json.dump(self._metrics[-1000:], f, default=str, indent=2)
            except Exception:
                pass

    def summary(self) -> Dict[str, Any]:
        """Summarize quality metrics."""
        if not self._metrics:
            return {"count": 0}
        
        by_kind: Dict[str, List[Dict[str, Any]]] = {}
        for m in self._metrics:
            kind = m.get("kind", "unknown")
            by_kind.setdefault(kind, []).append(m)

        return {
            "count": len(self._metrics),
            "by_kind": {k: len(v) for k, v in by_kind.items()},
            "latest": self._metrics[-1] if self._metrics else None,
        }

    def stats(self) -> Dict[str, Any]:
        return self.summary()


class OrganismState:
    """Central runtime state container for the Skeleton organism."""

    def __init__(self, bus: Optional[EventBus] = None):
        self.flags = FeatureFlags.from_env()
        self.health = HealthMonitor(bus=bus)
        self.quality: Optional[QualityState] = None
        self._start_time = time.time()
        self._metadata: Dict[str, Any] = {}

    def set_quality_root(self, root: Path) -> None:
        """Set the root directory for quality state persistence."""
        self.quality = QualityState(root=root)

    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def snapshot(self) -> Dict[str, Any]:
        """Capture full organism state."""
        return {
            "uptime_seconds": self.uptime_seconds(),
            "feature_flags": self.flags.to_dict(),
            "health": self.health.check().to_dict() if self.health else None,
            "quality": self.quality.summary() if self.quality else None,
            "metadata": dict(self._metadata),
        }

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def stats(self) -> Dict[str, Any]:
        return {
            "uptime_seconds": self.uptime_seconds(),
            "features_enabled": sum(1 for v in self.flags.to_dict().values() if v),
            "health_checks": len(self.health._checks) if self.health else 0,
        }


def append_quality(metric: Dict[str, Any], root: Optional[Path] = None) -> None:
    """Global helper to append a quality metric."""
    qs = QualityState(root=root)
    qs.append(metric)
