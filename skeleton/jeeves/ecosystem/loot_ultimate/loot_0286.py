"""Loot ultimate 0286.
"""
from __future__ import annotations

ID = "loot_ultimate_0286"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 286}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
