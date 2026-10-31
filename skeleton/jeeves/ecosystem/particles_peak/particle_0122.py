"""Particle peak 0122.
"""
from __future__ import annotations

ID = "particle_peak_0122"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 122}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
