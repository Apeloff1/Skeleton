"""Particle ultimate 0278.
"""
from __future__ import annotations

ID = "particle_ultimate_0278"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 278}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
