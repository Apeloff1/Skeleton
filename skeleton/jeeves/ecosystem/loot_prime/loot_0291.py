"""Loot prime 0291.
"""
from __future__ import annotations

ID = "loot_prime_0291"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 291}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
