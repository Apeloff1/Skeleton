"""Embedding shard 027.
"""
from __future__ import annotations

SHARD = 27
DIM = 16

def vector(key: str) -> list[float]:
    if not key:
        return [0.0] * DIM
    seed = sum(ord(c) for c in key) + SHARD * 17
    return [round(((seed * (n + 3)) % 997) / 997.0, 4) for n in range(DIM)]

def similarity(a: str, b: str) -> float:
    va, vb = vector(a), vector(b)
    dot = sum(x * y for x, y in zip(va, vb))
    return round(dot / DIM, 4)
