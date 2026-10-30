"""Particle advanced 0027.
"""
from __future__ import annotations

ID = "particle_adv_0027"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 27}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
