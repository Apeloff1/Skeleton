"""Loot eco_prime 0564.
"""
from __future__ import annotations

ID = "loot_eco_prime_0564"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 564}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
