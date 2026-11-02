"""Particle eco_prime 0133.
"""
from __future__ import annotations

ID = "particle_eco_prime_0133"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
