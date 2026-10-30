"""Cutscene scale 0011.
"""
from __future__ import annotations

ID = "cutscene_scale_0011"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 11}

def activate(context: str = "") -> dict:
    if not context and 11 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
