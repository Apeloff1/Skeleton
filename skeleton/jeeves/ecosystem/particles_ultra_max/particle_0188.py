"""Particle ultra_max 0188.
"""
from __future__ import annotations

ID = "particle_ultra_max_0188"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 188}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
