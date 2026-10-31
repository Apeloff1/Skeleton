"""Loot max 0154.
"""
from __future__ import annotations

ID = "loot_max_0154"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 154}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
