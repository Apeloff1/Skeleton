"""Dialogue advanced 0036.
"""
from __future__ import annotations

ID = "dialogue_adv_0036"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 36}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
