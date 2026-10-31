"""Loot apex 0212.
"""
from __future__ import annotations

ID = "loot_apex_0212"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 212}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
