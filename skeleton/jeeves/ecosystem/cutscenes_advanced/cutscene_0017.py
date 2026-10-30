"""Cutscene advanced 0017.
"""
from __future__ import annotations

ID = "cutscene_adv_0017"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
