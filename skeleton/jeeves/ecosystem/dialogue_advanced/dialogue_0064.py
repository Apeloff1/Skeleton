"""Dialogue advanced 0064.
"""
from __future__ import annotations

ID = "dialogue_adv_0064"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 64}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
