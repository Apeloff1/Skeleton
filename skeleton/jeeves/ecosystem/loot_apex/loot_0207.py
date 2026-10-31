"""Loot apex 0207.
"""
from __future__ import annotations

ID = "loot_apex_0207"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 207}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
