"""Particle eco_prime 0174.
"""
from __future__ import annotations

ID = "particle_eco_prime_0174"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 174}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
