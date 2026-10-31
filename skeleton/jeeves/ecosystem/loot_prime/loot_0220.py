"""Loot prime 0220.
"""
from __future__ import annotations

ID = "loot_prime_0220"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 220}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
