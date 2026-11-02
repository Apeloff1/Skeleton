"""Ach eco_apex 0120.
"""
from __future__ import annotations

ID = "ach_eco_apex_0120"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
