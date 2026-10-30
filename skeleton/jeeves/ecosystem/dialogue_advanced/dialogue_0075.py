"""Dialogue advanced 0075.
"""
from __future__ import annotations

ID = "dialogue_adv_0075"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 75}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
