"""Dialogue advanced 0059.
"""
from __future__ import annotations

ID = "dialogue_adv_0059"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 59}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
