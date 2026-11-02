"""Loot eco_apex 0099.
"""
from __future__ import annotations

ID = "loot_eco_apex_0099"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
