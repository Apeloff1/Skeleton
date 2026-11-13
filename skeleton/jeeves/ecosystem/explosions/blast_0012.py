"""Explosion 0012.
"""
from __future__ import annotations

BLAST = "blast_0012"

def detonate(radius: float = 3.0) -> dict:
    return {"ok": True, "blast": BLAST, "radius": max(0.5, radius), "damage": 20 + (12 % 15)}
