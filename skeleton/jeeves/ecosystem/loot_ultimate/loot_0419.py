"""Loot ultimate 0419.
"""
from __future__ import annotations

ID = "loot_ultimate_0419"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 419}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
