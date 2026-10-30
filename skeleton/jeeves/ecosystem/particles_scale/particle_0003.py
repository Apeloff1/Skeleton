"""Particle advanced 0003.
"""
from __future__ import annotations

ID = "particle_adv_0003"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 3}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
