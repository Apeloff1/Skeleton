"""Vfx scale 0001.
"""
from __future__ import annotations

ID = "vfx_scale_0001"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 1}

def activate(context: str = "") -> dict:
    if not context and 1 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
