"""Loot prime 0216.
"""
from __future__ import annotations

ID = "loot_prime_0216"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 216}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
