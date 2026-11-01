"""Loot ultimate 0344.
"""
from __future__ import annotations

ID = "loot_ultimate_0344"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 344}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
