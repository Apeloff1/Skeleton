"""Cutscene scale 0023.
"""
from __future__ import annotations

ID = "cutscene_scale_0023"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 23}

def activate(context: str = "") -> dict:
    if not context and 23 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
