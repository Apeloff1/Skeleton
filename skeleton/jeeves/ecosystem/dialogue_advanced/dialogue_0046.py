"""Dialogue advanced 0046.
"""
from __future__ import annotations

ID = "dialogue_adv_0046"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 46}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
