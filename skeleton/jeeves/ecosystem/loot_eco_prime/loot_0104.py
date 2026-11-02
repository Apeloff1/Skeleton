"""Loot eco_prime 0104.
"""
from __future__ import annotations

ID = "loot_eco_prime_0104"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 104}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
