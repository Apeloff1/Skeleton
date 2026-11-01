"""Particle ultimate 0227.
"""
from __future__ import annotations

ID = "particle_ultimate_0227"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 227}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
