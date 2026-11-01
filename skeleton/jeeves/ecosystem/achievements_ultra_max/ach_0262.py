"""Ach ultra_max 0262.
"""
from __future__ import annotations

ID = "ach_ultra_max_0262"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 262}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
