"""Loot ultimate 0332.
"""
from __future__ import annotations

ID = "loot_ultimate_0332"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 332}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
