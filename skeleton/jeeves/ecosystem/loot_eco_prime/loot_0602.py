"""Loot eco_prime 0602.
"""
from __future__ import annotations

ID = "loot_eco_prime_0602"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 602}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
