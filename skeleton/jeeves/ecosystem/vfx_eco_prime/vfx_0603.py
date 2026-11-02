"""Vfx eco_prime 0603.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0603"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 603}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
