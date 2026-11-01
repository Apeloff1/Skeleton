"""Ach ultimate 0273.
"""
from __future__ import annotations

ID = "ach_ultimate_0273"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
