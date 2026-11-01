"""Loot ultimate 0299.
"""
from __future__ import annotations

ID = "loot_ultimate_0299"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 299}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
