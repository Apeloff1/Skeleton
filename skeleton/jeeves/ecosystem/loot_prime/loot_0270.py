"""Loot prime 0270.
"""
from __future__ import annotations

ID = "loot_prime_0270"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 270}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
