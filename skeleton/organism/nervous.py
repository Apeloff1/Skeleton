"""Nervous system card — real-time subsystem health and telemetry.

Provides a live health card aggregating signals from all major
subsystems: policy, repair, lattice, steering, KV cache, mouth,
LoRA, decoder, swarm, telemetry, resilience, observability, and dashboard.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.cortex.deck import CommandDeck


def nervous_card(*, root=None) -> Dict[str, Any]:
    deck = CommandDeck(root=root)
    policy = deck.policy_state()
    repair = deck.repair_sessions()
    kv = deck.kv_cache_stats()
    mouth = deck.mouth_current()
    lora = deck.lora_card()
    decoder = deck.decoder_card()
    steering = deck.steering_composite()
    swarm = deck.swarm_card()
    telemetry = deck.telemetry_stats()
    benchmark = deck.benchmark_card()
    circuit = deck.circuit_card()
    load_shedder = deck.load_shedder_card()
    health = deck.health_probe_card()
    rate_limiter = deck.rate_limiter_card()
    tracer = deck.tracer_card()
    audit = deck.audit_card()
    event_store = deck.event_store_card()
    dashboard = deck.dashboard_card()
    return {
        "kind": "nervous-card",
        "health": {
            "policy_mean_threshold": policy.get("mean_threshold", 0.7),
            "repair_sessions_open": repair.get("total_sessions", 0) - repair.get("accepted_sessions", 0),
            "kv_cache_utilization": kv.get("entries", 0) / max(1, kv.get("max_entries", 1)),
            "mouth_viseme": mouth.get("viseme", "sil"),
            "lora_layers": lora.get("layers", 0),
            "decoder_patches": decoder.get("decode_count", 0),
            "steering_active": len(steering.get("card", {}).get("active_vectors", [])),
            "swarm_agents": swarm.get("agents", 0),
            "swarm_tasks_pending": swarm.get("pending_tasks", 0),
            "telemetry_events": telemetry.get("total_events", 0),
            "benchmark_runs": benchmark.get("runs", 0),
            "circuit_state": circuit.get("state", "closed"),
            "load_shedding_rate": load_shedder.get("shedding_rate", 0.0),
            "health_readiness": health.get("readiness", False),
            "health_liveness": health.get("liveness", False),
            "rate_limiter_keys": rate_limiter.get("keys", 0),
            "tracer_active_spans": tracer.get("active_spans", 0),
            "audit_entries": audit.get("total_entries", 0),
            "event_store_events": event_store.get("total_events", 0),
            "dashboard_alerts": dashboard.get("alert_counts", {}).get("critical", 0),
        },
        "alerts": [],
        "stored_prose": 0,
    }
