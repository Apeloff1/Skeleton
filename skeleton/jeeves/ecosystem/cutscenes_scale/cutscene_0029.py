"""Cutscene scale 0029.
"""
from __future__ import annotations

ID = "cutscene_scale_0029"

def describe() -> dict:
    return {"id": ID, "kind": "cutscene", "index": 29}

def activate(context: str = "") -> dict:
    if not context and 29 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
