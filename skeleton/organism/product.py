"""Operator-facing product card with full subsystem visibility.

Embeds policy state, version info, repair status, lattice, steering,
KV cache, mouth binding, LoRA, and decoder state into a single
operator-facing card.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.cortex.deck import CommandDeck


def product_card(*, root=None) -> Dict[str, Any]:
    deck = CommandDeck(root=root)
    return {
        "kind": "product-card",
        "policy": deck.policy_state(),
        "versions": deck.policy_versions(limit=4),
        "repair_orchestrator": deck.repair_orchestrate("forge", "_probe"),
        "lattice_hud": deck.lattice_hud(),
        "steering": deck.steering_composite(),
        "kv_cache": deck.kv_cache_stats(),
        "mouth": deck.mouth_current(),
        "lora": deck.lora_card(),
        "decoder": deck.decoder_card(),
        "stored_prose": 0,
    }
