"""Cutscene scale 0053.
"""
from __future__ import annotations

ID = "cutscene_scale_0053"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 53}

def activate(context: str = "") -> dict:
    if not context and 53 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
