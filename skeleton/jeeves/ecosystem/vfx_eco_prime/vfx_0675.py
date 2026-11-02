"""Vfx eco_prime 0675.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0675"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 675}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
