"""Explosion 0025.
"""
from __future__ import annotations

BLAST = "blast_0025"

def detonate(radius: float = 3.0) -> dict:
    return {"ok": True, "blast": BLAST, "radius": max(0.5, radius), "damage": 20 + (25 % 15)}
