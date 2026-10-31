"""Loot prime 0269.
"""
from __future__ import annotations

ID = "loot_prime_0269"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 269}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
