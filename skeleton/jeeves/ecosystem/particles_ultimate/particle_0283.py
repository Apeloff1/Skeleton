"""Particle ultimate 0283.
"""
from __future__ import annotations

ID = "particle_ultimate_0283"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 283}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
