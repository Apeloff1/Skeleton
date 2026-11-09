"""Clip law for the volume plane. No shard import."""

from __future__ import annotations

CLIP = 1.1
SEED = 8847291
STORED_PROSE = 0
PRIOR_X10_LINES = 153003200
X100_FUNCS = 850000
X100_SHARD_LINES = 7650009
X100_SHARD_BYTES = 303339093
X100_SHARDS = 200


def coeff(shard: int, index: int) -> int:
    return (SEED * 10007 + shard * 100003 + index * 97) & 0xFFFFFFFF


def clip_mass(proposed: float, prior: float) -> float:
    if prior <= 0:
        raise ValueError("prior")
    if proposed < 0:
        raise ValueError("mass")
    ceiling = prior * CLIP
    return ceiling if proposed > ceiling else proposed


def binding_mass(shard: int, index: int, prior: float = 1.0) -> float:
    value = coeff(shard, index)
    return clip_mass(prior * (1.0 + (value % 997) / 10000.0), prior)


def projection() -> dict[str, int]:
    projected = X100_SHARD_LINES * X100_SHARDS
    naive = PRIOR_X10_LINES * 10
    return {
        "shard_lines": X100_SHARD_LINES,
        "projected": projected,
        "naive": naive,
        "header_gap": naive - projected,
    }
