"""Explosion 0022.
"""
from __future__ import annotations

BLAST = "blast_0022"

def detonate(radius: float = 3.0) -> dict:
    return {"ok": True, "blast": BLAST, "radius": max(0.5, radius), "damage": 20 + (22 % 15)}
