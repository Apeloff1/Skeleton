"""Vfx eco_prime 0204.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0204"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 204}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
