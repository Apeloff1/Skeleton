"""Loot ultimate 0346.
"""
from __future__ import annotations

ID = "loot_ultimate_0346"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 346}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
