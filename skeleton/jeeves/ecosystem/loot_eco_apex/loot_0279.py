"""Loot eco_apex 0279.
"""
from __future__ import annotations

ID = "loot_eco_apex_0279"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 279}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
