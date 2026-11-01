"""Loot ultimate 0330.
"""
from __future__ import annotations

ID = "loot_ultimate_0330"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 330}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
