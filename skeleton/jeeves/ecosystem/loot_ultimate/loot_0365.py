"""Loot ultimate 0365.
"""
from __future__ import annotations

ID = "loot_ultimate_0365"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 365}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
