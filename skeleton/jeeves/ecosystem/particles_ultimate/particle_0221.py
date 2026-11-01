"""Particle ultimate 0221.
"""
from __future__ import annotations

ID = "particle_ultimate_0221"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 221}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
