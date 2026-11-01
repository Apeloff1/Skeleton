"""Particle ultra_max 0225.
"""
from __future__ import annotations

ID = "particle_ultra_max_0225"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 225}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
