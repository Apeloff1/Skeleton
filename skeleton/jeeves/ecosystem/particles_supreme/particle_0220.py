"""Particle supreme 0220.
"""
from __future__ import annotations

ID = "particle_supreme_0220"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 220}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
