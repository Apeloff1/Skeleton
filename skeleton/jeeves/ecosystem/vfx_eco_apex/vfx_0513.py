"""Vfx eco_apex 0513.
"""
from __future__ import annotations

ID = "vfx_eco_apex_0513"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 513}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
