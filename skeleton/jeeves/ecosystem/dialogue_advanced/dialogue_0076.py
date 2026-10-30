"""Dialogue advanced 0076.
"""
from __future__ import annotations

ID = "dialogue_adv_0076"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 76}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
