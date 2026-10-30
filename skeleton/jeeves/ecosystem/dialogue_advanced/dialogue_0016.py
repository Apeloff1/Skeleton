"""Dialogue advanced 0016.
"""
from __future__ import annotations

ID = "dialogue_adv_0016"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 16}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
