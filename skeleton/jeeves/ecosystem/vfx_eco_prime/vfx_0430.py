"""Vfx eco_prime 0430.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0430"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 430}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
