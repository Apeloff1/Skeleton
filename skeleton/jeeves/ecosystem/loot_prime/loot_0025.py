"""Loot prime 0025.
"""
from __future__ import annotations

ID = "loot_prime_0025"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 25}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
