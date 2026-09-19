"""GB-17 law constants. Kind count is frozen. Ring cap is frozen."""

from __future__ import annotations

PACKET = "GB-17"
LAYER = "primitives"
VERSION = "1.1"
PARENT = "#80"
CITATION = "docs/lineage/primitives.md"
RING_CAP = 24
KIND_COUNT = 12
STORED_PROSE = 0

# Twelve kinds. Do not grow this tuple. Tests fail if len != 12.
KINDS = (
    "bond",
    "quench",
    "witness",
    "gossip",
    "fork",
    "house",
    "compact",
    "silu",
    "gelu",
    "rms_norm",
    "ring",
    "merkle",
)

OPS = ("bond", "quench", "witness", "gossip", "fork", "house", "compact")
ACTIVATIONS = ("silu", "gelu", "rms_norm")
INFRA = ("ring", "merkle")

assert len(KINDS) == KIND_COUNT
assert set(OPS + ACTIVATIONS + INFRA) == set(KINDS)
