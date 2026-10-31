"""Vfx prime 0090.
"""
from __future__ import annotations

ID = "vfx_prime_0090"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 90}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
