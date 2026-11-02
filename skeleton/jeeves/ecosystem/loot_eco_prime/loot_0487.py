"""Loot eco_prime 0487.
"""
from __future__ import annotations

ID = "loot_eco_prime_0487"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 487}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
