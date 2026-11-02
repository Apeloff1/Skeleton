"""Loot eco_prime 0673.
"""
from __future__ import annotations

ID = "loot_eco_prime_0673"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 673}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
