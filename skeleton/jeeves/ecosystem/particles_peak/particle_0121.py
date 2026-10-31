"""Particle peak 0121.
"""
from __future__ import annotations

ID = "particle_peak_0121"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 121}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
