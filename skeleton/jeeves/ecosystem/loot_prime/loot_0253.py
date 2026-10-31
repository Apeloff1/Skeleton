"""Loot prime 0253.
"""
from __future__ import annotations

ID = "loot_prime_0253"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 253}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
