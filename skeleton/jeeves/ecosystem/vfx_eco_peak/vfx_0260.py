"""Vfx eco_peak 0260.
"""
from __future__ import annotations

ID = "vfx_eco_peak_0260"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 260}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
