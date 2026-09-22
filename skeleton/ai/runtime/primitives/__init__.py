"""Primitives 1.1 facade (GB-17). Thin. No viscera import. No artifact copy."""

from __future__ import annotations

from skeleton.primitives.activations import gelu, rms_norm, silu
from skeleton.primitives.capabilities import capabilities
from skeleton.primitives.cards import primitive_card
from skeleton.primitives.engine import PrimitiveEngine
from skeleton.primitives.kinds import kind_count, kind_set
from skeleton.primitives.law import KIND_COUNT, KINDS, RING_CAP
from skeleton.primitives.merkle import merkle_card, root_of
from skeleton.primitives.ops import bond, compact, fork, gossip, house, quench, witness
from skeleton.primitives.ring import Ring
from skeleton.primitives.viscera_bridge import viscera_card

__all__ = [
    "KIND_COUNT",
    "KINDS",
    "RING_CAP",
    "PrimitiveEngine",
    "Ring",
    "bond",
    "capabilities",
    "compact",
    "fork",
    "gelu",
    "gossip",
    "house",
    "kind_count",
    "kind_set",
    "merkle_card",
    "primitive_card",
    "quench",
    "rms_norm",
    "root_of",
    "silu",
    "viscera_card",
    "witness",
]
