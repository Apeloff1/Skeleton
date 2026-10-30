"""Particle mega 0001.
"""
from __future__ import annotations

ID = "particle_mega_0001"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 1}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
