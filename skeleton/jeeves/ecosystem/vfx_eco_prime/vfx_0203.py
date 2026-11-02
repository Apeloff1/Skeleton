"""Vfx eco_prime 0203.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0203"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 203}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
