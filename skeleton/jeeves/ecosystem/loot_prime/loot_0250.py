"""Loot prime 0250.
"""
from __future__ import annotations

ID = "loot_prime_0250"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 250}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
