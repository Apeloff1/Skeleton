"""Particle eco_peak 0373.
"""
from __future__ import annotations

ID = "particle_eco_peak_0373"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 373}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
