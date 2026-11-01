"""Ach ultra_max 0220.
"""
from __future__ import annotations

ID = "ach_ultra_max_0220"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 220}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
