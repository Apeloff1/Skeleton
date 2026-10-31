"""Loot apex 0225.
"""
from __future__ import annotations

ID = "loot_apex_0225"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 225}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
