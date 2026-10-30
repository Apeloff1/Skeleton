"""Particle mega 0005.
"""
from __future__ import annotations

ID = "particle_mega_0005"

def describe() -> dict:
    return {"id": ID, "kind": "particle", "index": 5}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
