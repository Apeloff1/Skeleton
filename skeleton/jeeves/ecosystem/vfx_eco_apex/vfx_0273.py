"""Vfx eco_apex 0273.
"""
from __future__ import annotations

ID = "vfx_eco_apex_0273"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
