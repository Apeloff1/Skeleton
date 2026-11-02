"""Vfx eco_apex 0403.
"""
from __future__ import annotations

ID = "vfx_eco_apex_0403"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 403}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
