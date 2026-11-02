"""Vfx eco_prime 0294.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0294"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 294}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
