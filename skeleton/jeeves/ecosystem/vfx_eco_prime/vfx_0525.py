"""Vfx eco_prime 0525.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0525"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 525}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
