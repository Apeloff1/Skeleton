"""Loot eco_prime 0575.
"""
from __future__ import annotations

ID = "loot_eco_prime_0575"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 575}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
