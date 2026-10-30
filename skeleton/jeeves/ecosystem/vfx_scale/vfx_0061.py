"""Vfx scale 0061.
"""
from __future__ import annotations

ID = "vfx_scale_0061"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 61}

def activate(context: str = "") -> dict:
    if not context and 61 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
