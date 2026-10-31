"""Vfx prime 0283.
"""
from __future__ import annotations

ID = "vfx_prime_0283"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 283}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
