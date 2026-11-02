"""Vfx eco_prime 0502.
"""
from __future__ import annotations

ID = "vfx_eco_prime_0502"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 502}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
