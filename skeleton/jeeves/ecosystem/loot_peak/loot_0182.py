"""Loot peak 0182.
"""
from __future__ import annotations

ID = "loot_peak_0182"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 182}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
