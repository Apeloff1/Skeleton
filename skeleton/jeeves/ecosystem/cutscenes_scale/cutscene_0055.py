"""Cutscene scale 0055.
"""
from __future__ import annotations

ID = "cutscene_scale_0055"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 55}

def activate(context: str = "") -> dict:
    if not context and 55 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
