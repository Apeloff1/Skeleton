"""Loot ultimate 0338.
"""
from __future__ import annotations

ID = "loot_ultimate_0338"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 338}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
