"""Vfx eco_peak 0427.
"""
from __future__ import annotations

ID = "vfx_eco_peak_0427"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 427}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
