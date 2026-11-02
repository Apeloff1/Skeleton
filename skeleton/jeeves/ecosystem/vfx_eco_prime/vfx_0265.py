"""Vfx eco_prime 0265.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0265"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 265}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
