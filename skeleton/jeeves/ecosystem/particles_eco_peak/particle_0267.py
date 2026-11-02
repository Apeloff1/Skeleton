"""Particle eco_peak 0267.
"""
from __future__ import annotations

ID = "particle_eco_peak_0267"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 267}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
