"""Loot peak 0192.
"""
from __future__ import annotations

ID = "loot_peak_0192"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 192}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
