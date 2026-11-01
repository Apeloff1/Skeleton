"""Particle supreme 0257.
"""
from __future__ import annotations

ID = "particle_supreme_0257"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 257}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
