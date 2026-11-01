"""Loot ultimate 0445.
"""
from __future__ import annotations

ID = "loot_ultimate_0445"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 445}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
