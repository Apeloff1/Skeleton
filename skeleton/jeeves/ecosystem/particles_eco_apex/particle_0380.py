"""Particle eco_apex 0380.
"""
from __future__ import annotations

ID = "particle_eco_apex_0380"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 380}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
