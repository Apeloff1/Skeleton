"""Ach ultra_max 0265.
"""
from __future__ import annotations

ID = "ach_ultra_max_0265"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 265}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
