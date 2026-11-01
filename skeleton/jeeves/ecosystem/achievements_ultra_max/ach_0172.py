"""Ach ultra_max 0172.
"""
from __future__ import annotations

ID = "ach_ultra_max_0172"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 172}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
