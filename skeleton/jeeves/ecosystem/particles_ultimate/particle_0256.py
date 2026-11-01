"""Particle ultimate 0256.
"""
from __future__ import annotations

ID = "particle_ultimate_0256"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 256}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
