"""Vfx ultimate 0189.
"""
from __future__ import annotations

ID = "vfx_ultimate_0189"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 189}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
