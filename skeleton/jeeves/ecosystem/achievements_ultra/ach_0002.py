"""Ach ultra 0002.
"""
from __future__ import annotations

ID = "ach_ultra_0002"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 2}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
