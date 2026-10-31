"""Particle ultra 0099.
"""
from __future__ import annotations

ID = "particle_ultra_0099"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
