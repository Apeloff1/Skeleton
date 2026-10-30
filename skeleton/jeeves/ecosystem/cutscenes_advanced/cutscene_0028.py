"""Cutscene advanced 0028.
"""
from __future__ import annotations

ID = "cutscene_adv_0028"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 28}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
