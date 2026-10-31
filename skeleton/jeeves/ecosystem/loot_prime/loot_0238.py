"""Loot prime 0238.
"""
from __future__ import annotations

ID = "loot_prime_0238"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 238}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
