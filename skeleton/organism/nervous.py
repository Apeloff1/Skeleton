"""Nervous system card — real-time subsystem health and telemetry.

Provides a live health card aggregating signals from all major
subsystems: policy, repair, lattice, steering, KV cache, mouth,
LoRA, and decoder.
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
        },
        "alerts": [],
        "stored_prose": 0,
    }
