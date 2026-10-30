"""Particle advanced 0025.
"""
from __future__ import annotations

ID = "particle_adv_0025"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 25}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
