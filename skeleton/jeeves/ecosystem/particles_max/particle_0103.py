"""Particle max 0103.
"""
from __future__ import annotations

ID = "particle_max_0103"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
