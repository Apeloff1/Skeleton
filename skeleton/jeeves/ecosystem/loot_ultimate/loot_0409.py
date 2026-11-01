"""Loot ultimate 0409.
"""
from __future__ import annotations

ID = "loot_ultimate_0409"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 409}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
