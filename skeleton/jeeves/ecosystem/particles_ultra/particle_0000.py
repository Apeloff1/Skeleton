"""Particle ultra 0000.
"""
from __future__ import annotations

ID = "particle_ultra_0000"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 0}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
