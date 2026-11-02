"""Vfx eco_prime 0505.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0505"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 505}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
