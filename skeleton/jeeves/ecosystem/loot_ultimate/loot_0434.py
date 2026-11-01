"""Loot ultimate 0434.
"""
from __future__ import annotations

ID = "loot_ultimate_0434"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 434}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
