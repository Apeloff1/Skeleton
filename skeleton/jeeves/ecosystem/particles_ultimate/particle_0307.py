"""Particle ultimate 0307.
"""
from __future__ import annotations

ID = "particle_ultimate_0307"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 307}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
