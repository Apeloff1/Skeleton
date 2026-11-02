"""Particle eco_prime 0573.
"""
from __future__ import annotations

ID = "particle_eco_prime_0573"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 573}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
