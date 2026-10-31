"""Explosion 0044.
"""
from __future__ import annotations

BLAST = "blast_0044"

def detonate(radius: float = 3.0) -> dict:
    return {"ok": True, "blast": BLAST, "radius": max(0.5, radius), "damage": 20 + (44 % 15)}
