"""Dialogue advanced 0014.
"""
from __future__ import annotations

ID = "dialogue_adv_0014"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 14}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
