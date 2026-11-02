"""Vfx eco_peak 0425.
"""
from __future__ import annotations

ID = "vfx_eco_peak_0425"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 425}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
