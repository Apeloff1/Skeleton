"""Particle peak 0102.
"""
from __future__ import annotations

ID = "particle_peak_0102"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 102}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
