"""Particle eco_peak 0180.
"""
from __future__ import annotations

ID = "particle_eco_peak_0180"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 180}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
