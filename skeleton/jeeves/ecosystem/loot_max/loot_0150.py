"""Loot max 0150.
"""
from __future__ import annotations

ID = "loot_max_0150"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 150}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
