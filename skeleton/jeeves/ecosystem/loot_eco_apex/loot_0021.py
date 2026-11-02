"""Loot eco_apex 0021.
"""
from __future__ import annotations

ID = "loot_eco_apex_0021"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 21}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
