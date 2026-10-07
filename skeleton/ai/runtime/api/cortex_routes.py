"""HTTP API routes for Skeleton cortex.

Provides REST endpoints for all subsystems: policy, repair, lattice,
steering, KV cache, mouth, LoRA, decoder, swarm, telemetry,
benchmark, deployment, resilience, observability, dashboard,
feature flags, config, schema registry, and secrets.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.cortex.deck import CommandDeck
from skeleton.cortex.operator_dashboard import OperatorDashboard


def register_routes(app, deck: CommandDeck) -> None:
    """Register all Skeleton API routes on a FastAPI/Flask app."""

    # ── Policy ──────────────────────────────────────────────

    @app.get("/api/v1/policy/state")
    def get_policy_state() -> Dict[str, Any]:
        return deck.policy_state()

    @app.get("/api/v1/policy/versions")
    def get_policy_versions(limit: int = 4) -> List[Dict[str, Any]]:
        return deck.policy_versions(limit=limit)

    @app.post("/api/v1/policy/rollback/{version}")
    def post_policy_rollback(version: str) -> Dict[str, Any]:
        return deck.policy_rollback(version)

    # ── Repair ──────────────────────────────────────────────

    @app.post("/api/v1/repair/orchestrate")
    def post_repair_orchestrate(surface: str = "forge", trigger: str = "_probe") -> Dict[str, Any]:
        return deck.repair_orchestrate(surface, trigger)

    @app.get("/api/v1/repair/sessions")
    def get_repair_sessions() -> Dict[str, Any]:
        return deck.repair_sessions()

    @app.get("/api/v1/repair/errors")
    def get_repair_errors() -> Dict[str, Any]:
        return deck.repair_errors()

    @app.get("/api/v1/repair/learned")
    def get_repair_learned() -> Dict[str, Any]:
        return deck.repair_learned()

    @app.get("/api/v1/repair/effectiveness")
    def get_repair_effectiveness() -> Dict[str, Any]:
        return deck.repair_effectiveness()

    @app.get("/api/v1/repair/telemetry")
    def get_repair_telemetry() -> Dict[str, Any]:
        return deck.repair_telemetry()

    # ── Lattice ─────────────────────────────────────────────

    @app.get("/api/v1/lattice/hud")
    def get_lattice_hud() -> Dict[str, Any]:
        return deck.lattice_hud()

    # ── Steering ────────────────────────────────────────────

    @app.get("/api/v1/steering/composite")
    def get_steering_composite() -> Dict[str, Any]:
        return deck.steering_composite()

    # ── KV Cache ────────────────────────────────────────────

    @app.get("/api/v1/kv/stats")
    def get_kv_stats() -> Dict[str, Any]:
        return deck.kv_cache_stats()

    # ── Mouth ───────────────────────────────────────────────

    @app.get("/api/v1/mouth/current")
    def get_mouth_current() -> Dict[str, Any]:
        return deck.mouth_current()

    # ── LoRA ────────────────────────────────────────────────

    @app.get("/api/v1/lora/card")
    def get_lora_card() -> Dict[str, Any]:
        return deck.lora_card()

    # ── Decoder ─────────────────────────────────────────────

    @app.get("/api/v1/decoder/card")
    def get_decoder_card() -> Dict[str, Any]:
        return deck.decoder_card()

    # ── Swarm ───────────────────────────────────────────────

    @app.get("/api/v1/swarm/card")
    def get_swarm_card() -> Dict[str, Any]:
        return deck.swarm_card()

    # ── Telemetry ───────────────────────────────────────────

    @app.get("/api/v1/telemetry/stats")
    def get_telemetry_stats() -> Dict[str, Any]:
        return deck.telemetry_stats()

    # ── Benchmark ───────────────────────────────────────────

    @app.get("/api/v1/benchmark/card")
    def get_benchmark_card() -> Dict[str, Any]:
        return deck.benchmark_card()

    # ── Deployment ──────────────────────────────────────────

    @app.get("/api/v1/deploy/manifests")
    def get_deploy_manifests() -> List[Dict[str, Any]]:
        return deck.deployment_manifests()

    # ── Resilience ──────────────────────────────────────────

    @app.get("/api/v1/resilience/circuit")
    def get_circuit_card() -> Dict[str, Any]:
        return deck.circuit_card()

    @app.get("/api/v1/resilience/retry")
    def get_retry_card() -> Dict[str, Any]:
        return deck.retry_card()

    @app.get("/api/v1/resilience/bulkhead")
    def get_bulkhead_card() -> Dict[str, Any]:
        return deck.bulkhead_card()

    @app.get("/api/v1/resilience/load-shedder")
    def get_load_shedder_card() -> Dict[str, Any]:
        return deck.load_shedder_card()

    @app.get("/api/v1/resilience/health")
    def get_health_card() -> Dict[str, Any]:
        return deck.health_probe_card()

    @app.get("/api/v1/resilience/rate-limiter")
    def get_rate_limiter_card() -> Dict[str, Any]:
        return deck.rate_limiter_card()

    # ── Observability ───────────────────────────────────────

    @app.get("/api/v1/observability/tracer")
    def get_tracer_card() -> Dict[str, Any]:
        return deck.tracer_card()

    @app.get("/api/v1/observability/audit")
    def get_audit_card() -> Dict[str, Any]:
        return deck.audit_card()

    @app.get("/api/v1/observability/audit/integrity")
    def get_audit_integrity() -> Dict[str, Any]:
        return deck.audit_integrity()

    @app.get("/api/v1/observability/events")
    def get_event_store_card() -> Dict[str, Any]:
        return deck.event_store_card()

    @app.get("/api/v1/observability/anomaly")
    def get_anomaly_card() -> Dict[str, Any]:
        return deck.anomaly_detector.card()

    @app.get("/api/v1/observability/metrics")
    def get_metrics_card() -> str:
        return deck.metrics.render()

    @app.post("/api/v1/observability/trace/{name}")
    def post_trace(name: str) -> Dict[str, Any]:
        span = deck.tracer.start_span(name)
        deck.tracer.finish_span(span)
        return {"traced": name, "span": span.to_dict()}

    @app.post("/api/v1/observability/audit/record")
    def post_audit_record(actor: str, action: str, resource: str) -> Dict[str, Any]:
        entry = deck.audit.record(actor, action, resource)
        return {"recorded": entry.to_dict()}

    @app.post("/api/v1/observability/events/append")
    def post_event_append(aggregate_id: str, event_type: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        event = deck.event_store.append(aggregate_id, event_type, payload or {})
        return {"appended": event.to_dict()}

    # ── Dashboard ───────────────────────────────────────────

    @app.get("/api/v1/dashboard/card")
    def get_dashboard_card() -> Dict[str, Any]:
        return deck.dashboard_card()

    @app.post("/api/v1/dashboard/alert")
    def post_dashboard_alert(severity: str, subsystem: str, message: str) -> Dict[str, Any]:
        alert = deck.dashboard.fire_alert(severity, subsystem, message)
        return {"fired": alert.to_dict()}

    @app.post("/api/v1/dashboard/alert/{alert_id}/ack")
    def post_ack_alert(alert_id: str) -> Dict[str, bool]:
        return {"acknowledged": deck.dashboard.acknowledge_alert(alert_id)}

    @app.post("/api/v1/dashboard/alert/{alert_id}/resolve")
    def post_resolve_alert(alert_id: str) -> Dict[str, bool]:
        return {"resolved": deck.dashboard.resolve_alert(alert_id)}

    # ── Feature Flags ───────────────────────────────────────

    @app.get("/api/v1/flags")
    def get_flags() -> Dict[str, Any]:
        return deck.feature_flag_card()

    @app.post("/api/v1/flags/{name}")
    def post_flag(name: str, enabled: bool = True, percentage: float = 100.0) -> Dict[str, Any]:
        deck.feature_flags.register(name, enabled=enabled, percentage=percentage)
        return {"registered": name}

    @app.get("/api/v1/flags/{name}")
    def get_flag(name: str, context: Dict[str, str] = None) -> Dict[str, bool]:
        return {"enabled": deck.feature_flags.is_enabled(name, context or {})}

    # ── Config ────────────────────────────────────────────

    @app.get("/api/v1/config")
    def get_config() -> Dict[str, Any]:
        return deck.config_card()

    @app.get("/api/v1/config/{path}")
    def get_config_path(path: str) -> Dict[str, Any]:
        return {"value": deck.config.get(path)}

    @app.post("/api/v1/config/{path}")
    def post_config_path(path: str, value: Any) -> Dict[str, Any]:
        deck.config.set(path, value)
        return {"set": path}

    # ── Schema Registry ───────────────────────────────────────

    @app.get("/api/v1/schema")
    def get_schema_registry() -> Dict[str, Any]:
        return deck.schema_card()

    @app.post("/api/v1/schema/{name}/{version}")
    def post_schema_register(name: str, version: int, schema: Dict[str, Any]) -> Dict[str, Any]:
        deck.schema_registry.register(name, version, schema)
        return {"registered": name, "version": version}

    @app.post("/api/v1/schema/{name}/validate")
    def post_schema_validate(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        errors = deck.schema_registry.validate(name, data)
        return {"valid": len(errors) == 0, "errors": errors}

    # ── Secrets ─────────────────────────────────────────────

    @app.get("/api/v1/secrets")
    def get_secrets() -> Dict[str, Any]:
        return deck.secret_card()

    @app.post("/api/v1/secrets/{name}")
    def post_secret_set(name: str, value: str) -> Dict[str, Any]:
        deck.secret_manager.set(name, value)
        return {"set": name}

    @app.get("/api/v1/secrets/{name}")
    def get_secret(name: str) -> Dict[str, Any]:
        return {"value": deck.secret_manager.get(name)}

    @app.post("/api/v1/secrets/{name}/rotate")
    def post_secret_rotate(name: str, value: str) -> Dict[str, Any]:
        deck.secret_manager.rotate(name, value)
        return {"rotated": name}

    # ── Meta ────────────────────────────────────────────────

    @app.get("/api/v1/meta")
    def get_meta() -> Dict[str, Any]:
        return deck.meta_card()
