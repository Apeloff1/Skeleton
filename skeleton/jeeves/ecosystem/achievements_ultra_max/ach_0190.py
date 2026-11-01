"""Ach ultra_max 0190.
"""
from __future__ import annotations

ID = "ach_ultra_max_0190"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 190}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
