"""Loot ultimate 0391.
"""
from __future__ import annotations

ID = "loot_ultimate_0391"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 391}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
