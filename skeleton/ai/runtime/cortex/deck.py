"""Command deck — unified operator interface for all Skeleton subsystems.

Aggregates policy, repair, lattice, steering, KV cache, mouth, LoRA,
decoder, swarm, telemetry, resilience, observability, dashboard, and
deployment subsystems into a single operator-facing API.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.deck_operations import DeckOperations
from skeleton.cortex.deck_interactions import DeckInteractions
from skeleton.cortex.operator_dashboard import OperatorDashboard
from skeleton.cortex.push_server import DashboardPushServer
from skeleton.observability.audit_logging import AuditLog
from skeleton.observability.distributed_tracing import Tracer
from skeleton.observability.event_sourcing import EventStore
from skeleton.observability.anomaly_detector import AnomalyDetector
from skeleton.observability.metrics_exporter import MetricsExporter
from skeleton.organism.config_manager import ConfigManager
from skeleton.organism.feature_flags import FeatureFlagRegistry
from skeleton.organism.schema_registry import SchemaRegistry
from skeleton.organism.secret_manager import SecretManager
from skeleton.resilience.envelope import CircuitBreaker
from skeleton.resilience.adaptive_retry import AdaptiveRetry
from skeleton.resilience.bulkhead import Bulkhead
from skeleton.automation.swarm.mesh import SwarmMesh
from dataclasses import asdict
from skeleton.resilience.auto_scaler import AutoScaler
from skeleton.resilience.health_probes import HealthProbeAggregator
from skeleton.resilience.load_shedder import LoadShedder
from skeleton.resilience.rate_limiter import RateLimiter


class CommandDeck(DeckOperations, DeckInteractions):
    """Unified operator interface aggregating all subsystems."""

    def __init__(self, neo=None, *, root: Optional[Path] = None):
        # Preserve the original positional path interface as well as model callers.
        if isinstance(neo, (str, Path)):
            if root is not None:
                raise TypeError("root supplied both positionally and by keyword")
            root, neo = neo, None
        self.root = Path(root) if root is not None else Path(".")
        self.neo = neo
        self._init_operations()
        self._init_interactions()
        self._init_subsystems()

    def _init_subsystems(self) -> None:
        # Observability
        self.tracer = Tracer("deck", sample_rate=1.0)
        self.audit = AuditLog(root=self.root)
        self.event_store = EventStore(root=self.root)
        self.anomaly_detector = AnomalyDetector("deck_latency")
        self.metrics = MetricsExporter("deck")

        # Resilience
        self.circuit = CircuitBreaker("deck")
        self.retry = AdaptiveRetry()
        self.bulkhead = Bulkhead(max_concurrent=10)
        self.swarm = SwarmMesh()
        self.load_shedder = LoadShedder("deck")
        self.health_probes = HealthProbeAggregator()
        self.rate_limiter = RateLimiter()
        self.auto_scaler = AutoScaler("deck")

        # Organism
        self.config = ConfigManager(root=self.root)
        self.feature_flags = FeatureFlagRegistry(root=self.root)
        self.schema_registry = SchemaRegistry()
        self.secret_manager = SecretManager(root=self.root)

        # Dashboard
        self.dashboard = OperatorDashboard(root=self.root, deck=self)
        self.push_server = DashboardPushServer(self.dashboard)

    # ── Swarm ───────────────────────────────────────────────

    def swarm_card(self) -> Dict[str, Any]:
        return self.swarm.stats()

    # ── Telemetry ───────────────────────────────────────────

    def telemetry_stats(self) -> Dict[str, Any]:
        return {**self.event_store.card(), "metrics": self.metrics.card()}

    # ── Benchmark ───────────────────────────────────────────

    def benchmark_card(self) -> Dict[str, Any]:
        return {"runs": 0, "status": "not_measured", "mean_latency_ms": None, "p99_latency_ms": None}

    # ── Resilience ──────────────────────────────────────────

    def circuit_card(self) -> Dict[str, Any]:
        return self.circuit.snapshot()

    def retry_card(self) -> Dict[str, Any]:
        return self.retry.card()

    def bulkhead_card(self) -> Dict[str, Any]:
        return asdict(self.bulkhead.status("deck"))

    def load_shedder_card(self) -> Dict[str, Any]:
        return self.load_shedder.card()

    def health_probe_card(self) -> Dict[str, Any]:
        return self.health_probes.card()

    def rate_limiter_card(self) -> Dict[str, Any]:
        return self.rate_limiter.card()

    # ── Deployment ──────────────────────────────────────────

    def deployment_manifests(self) -> List[Dict[str, Any]]:
        return []

    # ── Observability ───────────────────────────────────────

    def tracer_card(self) -> Dict[str, Any]:
        return self.tracer.card()

    def audit_card(self) -> Dict[str, Any]:
        return self.audit.card()

    def audit_integrity(self) -> Dict[str, Any]:
        return self.audit.verify_integrity()

    def event_store_card(self) -> Dict[str, Any]:
        return self.event_store.card()

    # ── Dashboard ───────────────────────────────────────────

    def dashboard_card(self) -> Dict[str, Any]:
        return self.dashboard.card()

    # ── Organism ────────────────────────────────────────────

    def feature_flag_card(self) -> Dict[str, Any]:
        return self.feature_flags.card()

    def config_card(self) -> Dict[str, Any]:
        return self.config.card()

    def schema_card(self) -> Dict[str, Any]:
        return self.schema_registry.card()

    def secret_card(self) -> Dict[str, Any]:
        return self.secret_manager.card()

    # ── Meta ────────────────────────────────────────────────

    def meta_card(self) -> Dict[str, Any]:
        return {
            "kind": "command-deck",
            "subsystems": [
                "policy", "repair", "lattice", "steering", "kv_cache",
                "mouth", "lora", "decoder", "swarm", "telemetry",
                "benchmark", "resilience", "deployment", "observability",
                "dashboard", "feature_flags", "config", "schema_registry", "secrets",
            ],
            "tracer": self.tracer.card(),
            "audit": self.audit.card(),
            "health": self.health_probes.card(),
        }


_LIVE = None


def live_deck(root=None) -> CommandDeck:
    """Process-local CommandDeck singleton (operator deck entrypoint)."""
    global _LIVE
    if _LIVE is None or (root is not None and getattr(_LIVE, "root", None) != root):
        _LIVE = CommandDeck(root=root)
    return _LIVE
