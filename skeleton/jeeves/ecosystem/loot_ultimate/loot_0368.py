"""Loot ultimate 0368.
"""
from __future__ import annotations

ID = "loot_ultimate_0368"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 368}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
