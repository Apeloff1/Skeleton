"""Vfx scale 0014.
"""
from __future__ import annotations

ID = "vfx_scale_0014"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 14}

def activate(context: str = "") -> dict:
    if not context and 14 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
