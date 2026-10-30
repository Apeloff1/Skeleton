"""Particle scale2 0036.
"""
from __future__ import annotations

ID = "particle_scale2_0036"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 36}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
