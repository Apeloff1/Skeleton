"""Particle supreme 0190.
"""
from __future__ import annotations

ID = "particle_supreme_0190"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 190}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
