"""Explosion 0009.
"""
from __future__ import annotations

BLAST = "blast_0009"

def detonate(radius: float = 3.0) -> dict:
    return {"ok": True, "blast": BLAST, "radius": max(0.5, radius), "damage": 20 + (9 % 15)}
