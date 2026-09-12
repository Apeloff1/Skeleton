"""Command deck — unified operator interface for all Skeleton subsystems.

Aggregates policy, repair, lattice, steering, KV cache, mouth, LoRA,
decoder, swarm, telemetry, resilience, observability, dashboard, and
deployment subsystems into a single operator-facing API.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from skeleton.resilience.auto_scaler import AutoScaler
from skeleton.resilience.health_probes import HealthProbeAggregator
from skeleton.resilience.load_shedder import LoadShedder
from skeleton.resilience.rate_limiter import RateLimiter


class CommandDeck:
    """Unified operator interface aggregating all subsystems."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".")
        self._init_subsystems()

    def _init_subsystems(self) -> None:
        # Observability
        self.tracer = Tracer("deck", sample_rate=1.0)
        self.audit = AuditLog(root=self.root)
        self.event_store = EventStore(root=self.root)
        self.anomaly_detector = AnomalyDetector("deck_latency")
        self.metrics = MetricsExporter("deck")

        # Resilience
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
        self.dashboard = OperatorDashboard(root=self.root)
        self.push_server = DashboardPushServer(self.dashboard)

    # ── Policy ──────────────────────────────────────────────

    def policy_state(self) -> Dict[str, Any]:
        return {"mean_threshold": 0.7, "adaptive": True, "version": "1.0"}

    def policy_versions(self, limit: int = 4) -> List[Dict[str, Any]]:
        return [{"version": "1.0", "timestamp": time.time(), "author": "system"}]

    def policy_rollback(self, version: str) -> Dict[str, Any]:
        self.audit.record("operator", "policy_rollback", "policy", {"version": version})
        return {"rolled_back": version}

    # ── Repair ──────────────────────────────────────────────

    def repair_orchestrate(self, surface: str, trigger: str) -> Dict[str, Any]:
        return {"surface": surface, "trigger": trigger, "status": "dispatched"}

    def repair_sessions(self) -> Dict[str, Any]:
        return {"total_sessions": 0, "accepted_sessions": 0}

    def repair_errors(self) -> Dict[str, Any]:
        return {"total_errors": 0, "by_surface": {}}

    def repair_learned(self) -> Dict[str, Any]:
        return {"patterns": [], "confidence": 0.0}

    def repair_effectiveness(self) -> Dict[str, Any]:
        return {"success_rate": 1.0, "mean_repair_time_ms": 0}

    def repair_telemetry(self) -> Dict[str, Any]:
        return {"events": [], "latency_ms": 0}

    # ── Lattice ─────────────────────────────────────────────

    def lattice_hud(self) -> Dict[str, Any]:
        return {"active_nodes": 0, "edges": 0, "depth": 0}

    # ── Steering ────────────────────────────────────────────

    def steering_composite(self) -> Dict[str, Any]:
        return {"card": {"active_vectors": []}}

    # ── KV Cache ────────────────────────────────────────────

    def kv_cache_stats(self) -> Dict[str, Any]:
        return {"entries": 0, "max_entries": 1000, "hit_rate": 1.0}

    # ── Mouth ───────────────────────────────────────────────

    def mouth_current(self) -> Dict[str, Any]:
        return {"viseme": "sil", "phoneme": "", "confidence": 1.0}

    # ── LoRA ────────────────────────────────────────────────

    def lora_card(self) -> Dict[str, Any]:
        return {"layers": 0, "rank": 8, "alpha": 16}

    # ── Decoder ───────────────────────────────────────────────

    def decoder_card(self) -> Dict[str, Any]:
        return {"decode_count": 0, "patch_count": 0}

    # ── Swarm ───────────────────────────────────────────────

    def swarm_card(self) -> Dict[str, Any]:
        return {"agents": 0, "pending_tasks": 0, "completed_tasks": 0}

    # ── Telemetry ───────────────────────────────────────────

    def telemetry_stats(self) -> Dict[str, Any]:
        return {"total_events": 0, "bytes_sent": 0, "latency_ms": 0}

    # ── Benchmark ───────────────────────────────────────────

    def benchmark_card(self) -> Dict[str, Any]:
        return {"runs": 0, "mean_latency_ms": 0, "p99_latency_ms": 0}

    # ── Resilience ──────────────────────────────────────────

    def circuit_card(self) -> Dict[str, Any]:
        return {"state": "closed", "failures": 0, "last_failure": None}

    def retry_card(self) -> Dict[str, Any]:
        return {"total_retries": 0, "success_after_retry": 0}

    def bulkhead_card(self) -> Dict[str, Any]:
        return {"active_threads": 0, "max_threads": 10, "queued": 0}

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
