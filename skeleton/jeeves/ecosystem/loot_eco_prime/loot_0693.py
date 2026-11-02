"""Loot eco_prime 0693.
"""
from __future__ import annotations

ID = "loot_eco_prime_0693"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 693}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
