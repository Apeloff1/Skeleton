"""Operator-facing product card with full subsystem visibility.

Embeds policy state, version info, repair status, lattice, steering,
KV cache, mouth binding, LoRA, decoder state, observability, and
dashboard state into a single operator-facing card.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.cortex.deck import CommandDeck


def product_card(org=None, *, neo=None, root=None, deck=None) -> Dict[str, Any]:
    deck = deck or CommandDeck(neo, root=getattr(org, "root", root))
    if org is not None:
        from skeleton import __version__
        from skeleton.organism.health import health_card
        from skeleton.research.social.field import field_card
        return {"kind": "product", "version": __version__, "target": org.TARGET,
                "health": health_card(org, neo=neo), "field": field_card()["pointers"],
                "endpoints": ["GET /cortex/product", "GET /cortex/ready"],
                "operator": deck.master_card(), "stored_prose": 0}
    return {
        "kind": "product-card",
        "policy": deck.policy_state(),
        "versions": deck.policy_versions(limit=4),
        "repair_orchestrator": deck.repair_sessions("forge"),
        "lattice_hud": deck.lattice_hud(),
        "steering": deck.steering_composite(),
        "kv_cache": deck.kv_cache_stats(),
        "mouth": deck.mouth_current(),
        "lora": deck.lora_card(),
        "decoder": deck.decoder_card(),
        "swarm": deck.swarm_card(),
        "telemetry": deck.telemetry_stats(),
        "benchmark": deck.benchmark_card(),
        "resilience": {
            "circuit": deck.circuit_card(),
            "retry": deck.retry_card(),
            "bulkhead": deck.bulkhead_card(),
            "load_shedder": deck.load_shedder_card(),
            "health_probes": deck.health_probe_card(),
            "rate_limiter": deck.rate_limiter_card(),
        },
        "deployment": deck.deployment_manifests(),
        "observability": {
            "tracer": deck.tracer_card(),
            "audit": deck.audit_card(),
            "event_store": deck.event_store_card(),
        },
        "dashboard": deck.dashboard.summary(),
        "feature_flags": deck.feature_flag_card(),
        "config": deck.config_card(),
        "schema_registry": deck.schema_card(),
        "secrets": deck.secret_card(),
        "stored_prose": 0,
    }
