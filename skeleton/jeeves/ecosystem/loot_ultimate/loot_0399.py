"""Loot ultimate 0399.
"""
from __future__ import annotations

ID = "loot_ultimate_0399"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 399}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
