"""Ach ultra_max 0280.
"""
from __future__ import annotations

ID = "ach_ultra_max_0280"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 280}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
