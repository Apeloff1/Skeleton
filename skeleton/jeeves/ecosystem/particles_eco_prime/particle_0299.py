"""Particle eco_prime 0299.
"""
from __future__ import annotations

ID = "particle_eco_prime_0299"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 299}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
