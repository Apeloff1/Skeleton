"""Cutscene scale2 0012.
"""
from __future__ import annotations

ID = "cutscene_scale2_0012"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 12}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
