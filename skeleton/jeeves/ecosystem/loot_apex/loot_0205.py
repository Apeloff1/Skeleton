"""Loot apex 0205.
"""
from __future__ import annotations

ID = "loot_apex_0205"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 205}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
