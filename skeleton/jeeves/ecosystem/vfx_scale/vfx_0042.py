"""Vfx scale 0042.
"""
from __future__ import annotations

ID = "vfx_scale_0042"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 42}

def activate(context: str = "") -> dict:
    if not context and 42 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
