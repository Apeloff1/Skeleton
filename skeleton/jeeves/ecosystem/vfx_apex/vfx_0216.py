"""Vfx apex 0216.
"""
from __future__ import annotations

ID = "vfx_apex_0216"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 216}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
