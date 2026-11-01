"""Ach ultra_max 0272.
"""
from __future__ import annotations

ID = "ach_ultra_max_0272"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 272}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
