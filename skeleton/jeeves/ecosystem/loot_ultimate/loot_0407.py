"""Loot ultimate 0407.
"""
from __future__ import annotations

ID = "loot_ultimate_0407"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 407}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
