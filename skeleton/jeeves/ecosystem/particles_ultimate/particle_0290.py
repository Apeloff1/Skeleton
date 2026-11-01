"""Particle ultimate 0290.
"""
from __future__ import annotations

ID = "particle_ultimate_0290"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 290}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
