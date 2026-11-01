"""Loot ultimate 0282.
"""
from __future__ import annotations

ID = "loot_ultimate_0282"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 282}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
