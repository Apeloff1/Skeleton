"""Particle ultra_max 0243.
"""
from __future__ import annotations

ID = "particle_ultra_max_0243"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 243}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
