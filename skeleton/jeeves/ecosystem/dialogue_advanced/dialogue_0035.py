"""Dialogue advanced 0035.
"""
from __future__ import annotations

ID = "dialogue_adv_0035"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 35}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
