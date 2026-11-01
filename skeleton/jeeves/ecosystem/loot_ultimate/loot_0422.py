"""Loot ultimate 0422.
"""
from __future__ import annotations

ID = "loot_ultimate_0422"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 422}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
