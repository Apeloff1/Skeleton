"""Vfx prime 0128.
"""
from __future__ import annotations

ID = "vfx_prime_0128"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 128}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
