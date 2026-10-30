"""Particle advanced 0026.
"""
from __future__ import annotations

ID = "particle_adv_0026"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 26}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
