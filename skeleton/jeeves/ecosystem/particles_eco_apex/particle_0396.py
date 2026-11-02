"""Particle eco_apex 0396.
"""
from __future__ import annotations

ID = "particle_eco_apex_0396"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 396}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
