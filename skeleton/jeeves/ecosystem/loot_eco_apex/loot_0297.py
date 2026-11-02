"""Loot eco_apex 0297.
"""
from __future__ import annotations

ID = "loot_eco_apex_0297"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 297}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
