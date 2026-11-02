"""Vfx eco_prime 0278.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0278"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 278}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
