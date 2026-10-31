"""Loot peak 0175.
"""
from __future__ import annotations

ID = "loot_peak_0175"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 175}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
