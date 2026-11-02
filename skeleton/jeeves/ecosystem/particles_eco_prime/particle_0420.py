"""Particle eco_prime 0420.
"""
from __future__ import annotations

ID = "particle_eco_prime_0420"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 420}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
