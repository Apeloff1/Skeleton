"""Particle ultimate 0237.
"""
from __future__ import annotations

ID = "particle_ultimate_0237"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 237}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
