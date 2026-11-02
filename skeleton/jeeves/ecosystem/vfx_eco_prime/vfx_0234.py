"""Vfx eco_prime 0234.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0234"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 234}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
