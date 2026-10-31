"""Particle peak 0134.
"""
from __future__ import annotations

ID = "particle_peak_0134"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 134}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
