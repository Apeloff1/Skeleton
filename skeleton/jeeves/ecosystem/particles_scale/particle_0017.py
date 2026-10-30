"""Particle advanced 0017.
"""
from __future__ import annotations

ID = "particle_adv_0017"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
