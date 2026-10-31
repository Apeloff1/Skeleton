"""Loot peak 0139.
"""
from __future__ import annotations

ID = "loot_peak_0139"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 139}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
