"""Particle eco_prime 0462.
"""
from __future__ import annotations

ID = "particle_eco_prime_0462"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 462}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
