"""Loot supreme 0090.
"""
from __future__ import annotations

ID = "loot_supreme_0090"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 90}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
