"""Dialogue advanced 0055.
"""
from __future__ import annotations

ID = "dialogue_adv_0055"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 55}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
