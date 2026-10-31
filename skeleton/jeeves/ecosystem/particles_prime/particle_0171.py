"""Particle prime 0171.
"""
from __future__ import annotations

ID = "particle_prime_0171"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 171}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
