"""Vfx scale2 0072.
"""
from __future__ import annotations

ID = "vfx_scale2_0072"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 72}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
