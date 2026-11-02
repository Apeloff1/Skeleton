"""Econ eco_supreme 0874.
"""
from __future__ import annotations

ID = "econ_eco_supreme_0874"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "index": 874}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
