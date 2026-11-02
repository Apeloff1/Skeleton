"""Loot eco_prime 0600.
"""
from __future__ import annotations

ID = "loot_eco_prime_0600"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 600}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
