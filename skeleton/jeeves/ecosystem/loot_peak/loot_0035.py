"""Loot peak 0035.
"""
from __future__ import annotations

ID = "loot_peak_0035"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 35}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
