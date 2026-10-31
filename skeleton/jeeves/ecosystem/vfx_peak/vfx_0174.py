"""Vfx peak 0174.
"""
from __future__ import annotations

ID = "vfx_peak_0174"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 174}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
