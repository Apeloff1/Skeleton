"""Particle ultra 0073.
"""
from __future__ import annotations

ID = "particle_ultra_0073"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 73}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
