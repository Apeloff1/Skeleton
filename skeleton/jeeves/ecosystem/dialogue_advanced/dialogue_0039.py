"""Dialogue advanced 0039.
"""
from __future__ import annotations

ID = "dialogue_adv_0039"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "index": 39}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
