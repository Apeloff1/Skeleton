"""Loot apex 0217.
"""
from __future__ import annotations

ID = "loot_apex_0217"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 217}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
